from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone

from .forms import EditarRecebimentoForm, PagamentoForm, RecebimentosForm
from .models import Pagamentos, Recebimentos


class FinancialFieldsFormTests(SimpleTestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.actual = timezone.now() - timedelta(days=1)

    def payment_payload(self, **changes):
        payload = {
            'tipo': 'M', 'valor_pagamento': '123.45',
            'data_vencimento': self.today.isoformat(),
        }
        payload.update(changes)
        return payload

    def receipt_payload(self, **changes):
        payload = {
            'valor_recebimento': '123.45', 'status_recebimento': 'False',
            'data_vencimento': self.today.isoformat(),
        }
        payload.update(changes)
        return payload

    def valid_instance(self, form):
        self.assertTrue(form.is_valid(), form.errors.as_json())
        return form.save(commit=False)

    def test_new_pending_payment_has_explicit_due_date_without_legacy_date(self):
        form = PagamentoForm(self.payment_payload())
        payment = self.valid_instance(form)
        self.assertEqual(payment.data_vencimento, self.today)
        self.assertIsNone(payment.data_pagamento)
        self.assertIsNone(payment.data_pagamento_realizado)
        self.assertNotIn('data_pagamento', form.fields)

    def test_new_movements_require_amount_and_due_date(self):
        for form_class, payload, amount in (
            (PagamentoForm, self.payment_payload(), 'valor_pagamento'),
            (RecebimentosForm, self.receipt_payload(), 'valor_recebimento'),
        ):
            for missing in (amount, 'data_vencimento'):
                with self.subTest(form=form_class.__name__, missing=missing):
                    data = {key: value for key, value in payload.items() if key != missing}
                    form = form_class(data)
                    self.assertFalse(form.is_valid())
                    self.assertIn(missing, form.errors)

    def test_amounts_must_be_positive(self):
        for value in ('0', '-0.01'):
            for form_class, payload, amount in (
                (PagamentoForm, self.payment_payload(), 'valor_pagamento'),
                (RecebimentosForm, self.receipt_payload(), 'valor_recebimento'),
            ):
                with self.subTest(form=form_class.__name__, value=value):
                    payload[amount] = value
                    form = form_class(payload)
                    self.assertFalse(form.is_valid())
                    self.assertIn(amount, form.errors)

    def test_new_paid_payment_requires_actual_payment_date(self):
        form = PagamentoForm(self.payment_payload(status_pagamento='on'))
        self.assertFalse(form.is_valid())
        self.assertIn('data_pagamento_realizado', form.errors)
        payment = self.valid_instance(PagamentoForm(self.payment_payload(
            status_pagamento='on', data_pagamento_realizado=self.today.isoformat(),
        )))
        self.assertTrue(payment.status_pagamento)
        self.assertEqual(payment.data_pagamento_realizado, self.today)

    def test_payment_actual_date_cannot_be_in_the_future(self):
        form = PagamentoForm(self.payment_payload(
            status_pagamento='on',
            data_pagamento_realizado=(self.today + timedelta(days=1)).isoformat(),
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('data_pagamento_realizado', form.errors)

    def test_legacy_payment_preserves_unknown_dates_and_legacy_value(self):
        original_date = self.today - timedelta(days=120)
        payment = Pagamentos(
            pk=23, tipo='M', valor_pagamento=None, data_pagamento=original_date,
            status_pagamento=True,
        )
        saved = self.valid_instance(PagamentoForm(
            {'tipo': 'M', 'status_pagamento': 'on'}, instance=payment,
        ))
        self.assertIsNone(saved.valor_pagamento)
        self.assertIsNone(saved.data_vencimento)
        self.assertIsNone(saved.data_pagamento_realizado)
        self.assertEqual(saved.data_pagamento, original_date)

    def test_legacy_pending_to_paid_requires_actual_date(self):
        payment = Pagamentos(pk=23, tipo='M', valor_pagamento=Decimal('10.00'))
        form = PagamentoForm({'tipo': 'M', 'status_pagamento': 'on'}, instance=payment)
        self.assertFalse(form.is_valid())
        self.assertIn('data_pagamento_realizado', form.errors)

    def test_omitted_financial_fields_keep_existing_payment_values(self):
        payment = Pagamentos(
            pk=23, tipo='M', valor_pagamento=Decimal('45.67'), status_pagamento=True,
            data_vencimento=self.today, data_pagamento_realizado=self.today,
        )
        saved = self.valid_instance(PagamentoForm(
            {'tipo': 'T', 'status_pagamento': 'on'}, instance=payment,
        ))
        self.assertEqual(saved.valor_pagamento, Decimal('45.67'))
        self.assertEqual(saved.data_vencimento, self.today)
        self.assertEqual(saved.data_pagamento_realizado, self.today)

    def test_reopening_a_payment_clears_only_effective_date(self):
        payment = Pagamentos(
            pk=23, tipo='M', status_pagamento=True, data_pagamento=self.today,
            data_pagamento_realizado=self.today,
        )
        saved = self.valid_instance(PagamentoForm({'tipo': 'M'}, instance=payment))
        self.assertFalse(saved.status_pagamento)
        self.assertIsNone(saved.data_pagamento_realizado)
        self.assertEqual(saved.data_pagamento, self.today)

    def test_unpaid_movement_cannot_acquire_new_effective_date(self):
        form = PagamentoForm(self.payment_payload(data_pagamento_realizado=self.today.isoformat()))
        self.assertFalse(form.is_valid())
        self.assertIn('data_pagamento_realizado', form.errors)

    def test_receipt_confirmation_is_derived_from_status_and_forged_checkbox_ignored(self):
        form = RecebimentosForm(self.receipt_payload(recebimento_realizado='on'))
        receipt = self.valid_instance(form)
        self.assertNotIn('recebimento_realizado', form.fields)
        self.assertFalse(receipt.status_recebimento)
        self.assertFalse(receipt.recebimento_realizado)

    def test_new_received_movement_requires_actual_date_and_syncs_confirmation(self):
        form = RecebimentosForm(self.receipt_payload(status_recebimento='True'))
        self.assertFalse(form.is_valid())
        self.assertIn('data_recebimento_realizado', form.errors)
        receipt = self.valid_instance(RecebimentosForm(self.receipt_payload(
            status_recebimento='True', data_recebimento_realizado=self.actual.isoformat(),
        )))
        self.assertTrue(receipt.status_recebimento)
        self.assertTrue(receipt.recebimento_realizado)
        self.assertEqual(receipt.data_recebimento_realizado, self.actual)

    def test_received_movement_cannot_have_future_actual_date(self):
        future = timezone.now() + timedelta(days=2)
        form = RecebimentosForm(self.receipt_payload(
            status_recebimento='True', data_recebimento_realizado=future.isoformat(),
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('data_recebimento_realizado', form.errors)

    def test_receipt_actual_timestamp_cannot_be_in_the_future_today(self):
        future = timezone.now() + timedelta(minutes=1)
        form = RecebimentosForm(self.receipt_payload(
            status_recebimento='True', data_recebimento_realizado=future.isoformat(),
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('data_recebimento_realizado', form.errors)

    def test_legacy_receipt_unknown_fields_are_not_filled_during_edit(self):
        receipt = Recebimentos(pk=42, status_recebimento=True)
        saved = self.valid_instance(EditarRecebimentoForm(
            {'status_recebimento': 'True', 'descricao_recebimento': 'Histórico'}, instance=receipt,
        ))
        self.assertIsNone(saved.valor_recebimento)
        self.assertIsNone(saved.data_vencimento)
        self.assertIsNone(saved.data_recebimento_realizado)
        self.assertTrue(saved.recebimento_realizado)

    def test_unchanged_pending_receipt_keeps_historical_actual_date(self):
        receipt = Recebimentos(
            pk=42, status_recebimento=False, recebimento_realizado=True,
            data_recebimento_realizado=self.actual,
        )
        saved = self.valid_instance(EditarRecebimentoForm(
            {'status_recebimento': 'False', 'descricao_recebimento': 'Histórico'}, instance=receipt,
        ))
        self.assertFalse(saved.status_recebimento)
        self.assertFalse(saved.recebimento_realizado)
        self.assertEqual(saved.data_recebimento_realizado, self.actual)

    def test_blank_effective_date_does_not_erase_received_date_without_reopening(self):
        receipt = Recebimentos(
            pk=42, status_recebimento=True, data_recebimento_realizado=self.actual,
        )
        saved = self.valid_instance(EditarRecebimentoForm({
            'status_recebimento': 'True', 'data_recebimento_realizado': '',
        }, instance=receipt))
        self.assertEqual(saved.data_recebimento_realizado, self.actual)

    def test_pending_legacy_payment_keeps_omitted_effective_date(self):
        payment = Pagamentos(
            pk=23, tipo='M', status_pagamento=False,
            data_pagamento_realizado=self.today,
        )
        saved = self.valid_instance(PagamentoForm({'tipo': 'M'}, instance=payment))
        self.assertFalse(saved.status_pagamento)
        self.assertEqual(saved.data_pagamento_realizado, self.today)

    def test_explicit_blank_clears_inconsistent_effective_date_in_pending_movements(self):
        payment = Pagamentos(
            pk=23, tipo='M', status_pagamento=False,
            data_pagamento_realizado=self.today,
        )
        saved_payment = self.valid_instance(PagamentoForm({
            'tipo': 'M', 'data_pagamento_realizado': '',
        }, instance=payment))
        self.assertFalse(saved_payment.status_pagamento)
        self.assertIsNone(saved_payment.data_pagamento_realizado)

        receipt = Recebimentos(
            pk=42, status_recebimento=False, recebimento_realizado=True,
            data_recebimento_realizado=self.actual,
        )
        saved_receipt = self.valid_instance(EditarRecebimentoForm({
            'status_recebimento': 'False', 'data_recebimento_realizado': '',
        }, instance=receipt))
        self.assertFalse(saved_receipt.status_recebimento)
        self.assertFalse(saved_receipt.recebimento_realizado)
        self.assertIsNone(saved_receipt.data_recebimento_realizado)

    def test_reopening_received_movement_clears_effective_date_and_confirmation(self):
        receipt = Recebimentos(
            pk=42, status_recebimento=True, recebimento_realizado=True,
            data_recebimento_realizado=self.actual,
        )
        saved = self.valid_instance(EditarRecebimentoForm(
            {'status_recebimento': 'False'}, instance=receipt,
        ))
        self.assertFalse(saved.recebimento_realizado)
        self.assertIsNone(saved.data_recebimento_realizado)

    def test_receipt_datetime_widget_keeps_microseconds_when_unchanged(self):
        receipt = Recebimentos(
            pk=42, status_recebimento=True, data_recebimento_realizado=self.actual,
        )
        form = EditarRecebimentoForm({
            'status_recebimento': 'True',
            'data_recebimento_realizado': self.actual.replace(microsecond=0).isoformat(),
        }, instance=receipt)
        saved = self.valid_instance(form)
        self.assertEqual(saved.data_recebimento_realizado, self.actual)
        self.assertIn('type="datetime-local"', str(form['data_recebimento_realizado']))

    def test_changing_pending_receipt_to_received_requires_actual_date(self):
        receipt = Recebimentos(pk=42, status_recebimento=False)
        form = EditarRecebimentoForm({'status_recebimento': 'True'}, instance=receipt)
        self.assertFalse(form.is_valid())
        self.assertIn('data_recebimento_realizado', form.errors)

    def test_unchanged_future_historical_receipt_date_is_not_rewritten(self):
        historical_date = timezone.now() + timedelta(days=2)
        receipt = Recebimentos(
            pk=42, status_recebimento=True, data_recebimento_realizado=historical_date,
        )
        saved = self.valid_instance(EditarRecebimentoForm(
            {'status_recebimento': 'True'}, instance=receipt,
        ))
        self.assertEqual(saved.data_recebimento_realizado, historical_date)

    def test_payment_model_dates_are_nullable_without_inferred_defaults(self):
        for name in ('data_pagamento', 'data_vencimento', 'data_pagamento_realizado'):
            field = Pagamentos._meta.get_field(name)
            self.assertTrue(field.null)
            self.assertFalse(field.has_default())
        self.assertTrue(Pagamentos._meta.get_field('data_vencimento').db_index)
