from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rolepermissions.roles import assign_role

from .models import Recebimentos, Ticket


@override_settings(TIME_ZONE='America/Sao_Paulo')
class EditarRecebimentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='operador_recebimento')
        assign_role(cls.owner, 'operador')
        cls.other_user = User.objects.create_user(username='outro_recebimento')
        assign_role(cls.other_user, 'operador')
        cls.staff_user = User.objects.create_user(
            username='staff_recebimento', is_staff=True,
        )
        cls.manager = User.objects.create_user(username='gerente_recebimento')
        assign_role(cls.manager, 'gerente')
        cls.administrator = User.objects.create_superuser(
            username='admin_recebimento', email='admin@example.invalid',
            password='test-only-password',
        )
        cls.ticket = Ticket.objects.create(
            ticket='RECEDIT001', usuario=cls.owner,
            descricao='Ticket fictício para edição de recebimento',
        )
        cls.other_ticket = Ticket.objects.create(
            ticket='RECEDIT002', usuario=cls.other_user,
            descricao='Outro ticket fictício',
        )
        cls.original_timestamp = datetime(
            2026, 10, 5, 14, 23, 45, 654321,
            tzinfo=ZoneInfo('America/Sao_Paulo'),
        )
        cls.recebimento = Recebimentos.objects.create(
            ticket_recebimento=cls.ticket,
            razao_social='Empresa fictícia do recebimento',
            numero_nota_fiscal='NF-ORIGINAL', serie_nota_fiscal='A',
            data_emissao=date(2026, 9, 29),
            data_vencimento=date(2026, 10, 20),
            valor_recebimento=Decimal('125.40'), status_recebimento=True,
            descricao_recebimento='Recebimento original',
            forma_pagamento='À vista', tipo_pagamento='Pix',
            comprovante_recebimento='comprovantes/recebimento-ficticio.pdf',
            recebimento_realizado=True,
            data_recebimento_realizado=cls.original_timestamp,
        )
        cls.other_receipt = Recebimentos.objects.create(
            ticket_recebimento=cls.other_ticket,
            numero_nota_fiscal='NF-OUTRO',
            valor_recebimento=Decimal('88.00'), status_recebimento=False,
        )

    def setUp(self):
        current_timezone = timezone.override('America/Sao_Paulo')
        current_timezone.__enter__()
        self.addCleanup(current_timezone.__exit__, None, None, None)
        self.url = reverse('editar-recebimento', kwargs={
            'recebimento_id': self.recebimento.pk, 'key': self.ticket.key,
        })
        self.detail_url = reverse('exibir-ticket', kwargs={'key': self.ticket.key})
        self.client.force_login(self.owner)

    def valid_payload(self, **changes):
        payload = {
            'numero_nota_fiscal': 'NF-CORRIGIDA',
            'serie_nota_fiscal': 'B',
            'data_emissao': '2026-10-01',
            'data_vencimento': '2026-10-31',
            'valor_recebimento': '2345.67',
            'status_recebimento': 'True',
            'descricao_recebimento': 'Recebimento corrigido',
            'forma_pagamento': 'A Prazo',
            'tipo_pagamento': 'Transferência Bancária',
            'recebimento_realizado': 'on',
            'data_recebimento_realizado': '2026-10-05T14:23:45',
        }
        payload.update(changes)
        return payload

    def receipt_snapshot(self, receipt=None):
        receipt = receipt or self.recebimento
        return Recebimentos.objects.filter(pk=receipt.pk).values().get()

    def assert_saved_to_ticket(self, response):
        self.assertRedirects(
            response, f'{self.detail_url}#recebimentos', fetch_redirect_response=False,
        )

    def test_anonymous_requests_redirect_to_login_without_saving(self):
        before = self.receipt_snapshot()
        self.client.logout()
        for method in ('get', 'post'):
            with self.subTest(method=method):
                request = getattr(self.client, method)
                response = request(self.url, self.valid_payload() if method == 'post' else {})
                self.assertEqual(response.status_code, 302)
                self.assertIn('/accounts/login/', response.url)
                self.assertIn('next=', response.url)
                self.assertEqual(self.receipt_snapshot(), before)

    def test_owner_get_prefills_iso_dates_and_seconds_without_persisting(self):
        before = self.receipt_snapshot()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tickets/editar-recebimento.html')
        form = response.context['form']
        self.assertEqual(form.instance.pk, self.recebimento.pk)
        self.assertTrue(form.fields['status_recebimento'].required)
        for field, expected in (
            ('data_emissao', '2026-09-29'),
            ('data_vencimento', '2026-10-20'),
        ):
            with self.subTest(field=field):
                self.assertIn('type="date"', str(form[field]))
                self.assertIn(f'value="{expected}"', str(form[field]))
        timestamp_input = str(form['data_recebimento_realizado'])
        self.assertIn('type="datetime-local"', timestamp_input)
        self.assertIn('step="1"', timestamp_input)
        self.assertIn('value="2026-10-05T14:23:45"', timestamp_input)
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, self.url)
        self.assertTrue(detail.context['can_edit_recebimentos'])
        self.assertEqual(self.receipt_snapshot(), before)
        self.assertEqual(Recebimentos.objects.count(), 2)

    def test_post_updates_same_record_and_preserves_protected_fields_and_fraction(self):
        before = self.receipt_snapshot()
        response = self.client.post(self.url, self.valid_payload())
        self.assert_saved_to_ticket(response)
        self.recebimento.refresh_from_db()
        self.assertEqual(Recebimentos.objects.count(), 2)
        self.assertEqual(self.recebimento.pk, before['id'])
        for field in (
            'ticket_recebimento_id', 'data_recebimento', 'razao_social',
            'comprovante_recebimento',
        ):
            with self.subTest(field=field):
                self.assertEqual(getattr(self.recebimento, field), before[field])
        self.assertEqual(self.recebimento.valor_recebimento, Decimal('2345.67'))
        self.assertEqual(self.recebimento.numero_nota_fiscal, 'NF-CORRIGIDA')
        self.assertEqual(self.recebimento.serie_nota_fiscal, 'B')
        self.assertEqual(self.recebimento.data_emissao, date(2026, 10, 1))
        self.assertEqual(self.recebimento.data_vencimento, date(2026, 10, 31))
        self.assertEqual(self.recebimento.descricao_recebimento, 'Recebimento corrigido')
        self.assertEqual(self.recebimento.forma_pagamento, 'A Prazo')
        self.assertEqual(self.recebimento.tipo_pagamento, 'Transferência Bancária')
        self.assertTrue(self.recebimento.status_recebimento)
        self.assertTrue(self.recebimento.recebimento_realizado)
        self.assertEqual(self.recebimento.data_recebimento_realizado, self.original_timestamp)
        self.assertEqual(self.recebimento.data_recebimento_realizado.microsecond, 654321)

    def test_invalid_amount_date_or_missing_status_shows_errors_without_saving(self):
        before = self.receipt_snapshot()
        for field, invalid_value in (
            ('valor_recebimento', 'valor inválido'),
            ('data_emissao', '2026-02-30'),
            ('status_recebimento', None),
        ):
            with self.subTest(field=field):
                payload = self.valid_payload()
                if invalid_value is None:
                    payload.pop(field)
                else:
                    payload[field] = invalid_value
                response = self.client.post(self.url, payload)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'tickets/editar-recebimento.html')
                form = response.context['form']
                self.assertIn(field, form.errors)
                self.assertContains(response, str(form.errors[field][0]))
                if invalid_value is not None:
                    self.assertEqual(form[field].value(), invalid_value)
                self.assertEqual(self.receipt_snapshot(), before)
                self.assertEqual(Recebimentos.objects.count(), 2)

    def test_other_users_cannot_edit_or_see_the_edit_link(self):
        before = self.receipt_snapshot()
        for user in (self.other_user, self.staff_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                for method in ('get', 'post'):
                    with self.subTest(method=method):
                        request = getattr(self.client, method)
                        response = request(
                            self.url, self.valid_payload() if method == 'post' else {},
                        )
                        self.assertEqual(response.status_code, 404)
                detail = self.client.get(self.detail_url)
                self.assertNotContains(detail, self.url)
                self.assertFalse(detail.context['can_edit_recebimentos'])
                self.assertEqual(self.receipt_snapshot(), before)

    def test_manager_and_superuser_can_edit_another_users_receipt(self):
        for user, amount in (
            (self.manager, '501.10'), (self.administrator, '502.20'),
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                detail = self.client.get(self.detail_url)
                self.assertContains(detail, self.url)
                self.assertTrue(detail.context['can_edit_recebimentos'])
                response = self.client.post(
                    self.url, self.valid_payload(valor_recebimento=amount),
                )
                self.assert_saved_to_ticket(response)
                self.recebimento.refresh_from_db()
                self.assertEqual(self.recebimento.valor_recebimento, Decimal(amount))
                self.assertEqual(self.recebimento.ticket_recebimento_id, self.ticket.pk)
                self.assertEqual(Recebimentos.objects.count(), 2)

    def test_receipt_from_another_ticket_returns_404_without_saving(self):
        url = reverse('editar-recebimento', kwargs={
            'recebimento_id': self.other_receipt.pk, 'key': self.ticket.key,
        })
        original = self.receipt_snapshot()
        other = self.receipt_snapshot(self.other_receipt)
        for method in ('get', 'post'):
            with self.subTest(method=method):
                request = getattr(self.client, method)
                response = request(url, self.valid_payload() if method == 'post' else {})
                self.assertEqual(response.status_code, 404)
                self.assertEqual(self.receipt_snapshot(), original)
                self.assertEqual(self.receipt_snapshot(self.other_receipt), other)

    def test_forged_foreign_key_and_protected_fields_are_ignored(self):
        before = self.receipt_snapshot()
        other = self.receipt_snapshot(self.other_receipt)
        payload = self.valid_payload(
            ticket_recebimento=str(self.other_ticket.pk),
            ticket_recebimento_id=str(self.other_ticket.pk),
            razao_social='Razão social forjada',
            comprovante_recebimento='comprovantes/forjado.pdf',
            data_recebimento='2000-01-01T00:00:00',
            id=str(self.other_receipt.pk),
        )
        response = self.client.post(self.url, payload)
        self.assert_saved_to_ticket(response)
        self.recebimento.refresh_from_db()
        for field in (
            'id', 'ticket_recebimento_id', 'razao_social',
            'comprovante_recebimento', 'data_recebimento',
        ):
            with self.subTest(field=field):
                self.assertEqual(getattr(self.recebimento, field), before[field])
        self.assertEqual(self.recebimento.valor_recebimento, Decimal('2345.67'))
        self.assertEqual(self.receipt_snapshot(self.other_receipt), other)
        self.assertEqual(Recebimentos.objects.count(), 2)

    def test_changed_timestamp_uses_submitted_seconds_and_false_status_is_valid(self):
        payload = self.valid_payload(
            data_recebimento_realizado='2026-10-06T10:11:12',
            status_recebimento='False',
        )
        response = self.client.post(self.url, payload)
        self.assert_saved_to_ticket(response)
        self.recebimento.refresh_from_db()
        expected = datetime(
            2026, 10, 6, 10, 11, 12, tzinfo=ZoneInfo('America/Sao_Paulo'),
        )
        self.assertEqual(self.recebimento.data_recebimento_realizado, expected)
        self.assertEqual(self.recebimento.data_recebimento_realizado.microsecond, 0)
        self.assertFalse(self.recebimento.status_recebimento)
