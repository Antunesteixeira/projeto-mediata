import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rolepermissions.roles import assign_role

from clientes.models import Cliente
from insumos.models import Insumos
from .models import Ticket, Orcamento, ItemOrcamento, Pagamentos, Recebimentos, HistoricoTicket, Anexo
from .reports import ticket_report


class TicketPDFTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='operador', password='test-only-password', first_name='Operador', last_name='Responsável')
        self.ticket = Ticket.objects.create(ticket='PDF001', usuario=self.user, descricao='Descrição completa\nSegunda linha')
        self.url = reverse('gerar_pdf_ticket', kwargs={'key': self.ticket.key})

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_ticket_page_has_full_pdf_button_without_budget(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('exibir-ticket', kwargs={'key': self.ticket.key}))
        self.assertContains(response, 'PDF completo')
        self.assertContains(response, self.url)

    def test_unknown_ticket_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('gerar_pdf_ticket', kwargs={'key': uuid.uuid4()}))
        self.assertEqual(response.status_code, 404)

    @patch('tickets.views.HTML')
    def test_other_users_cannot_export_ticket(self, renderer):
        for role in ('operador', 'cliente', 'colaborador'):
            with self.subTest(role=role):
                other_user = User.objects.create_user(username=f'outro_{role}')
                assign_role(other_user, role)
                self.client.force_login(other_user)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 404)
        renderer.assert_not_called()

    @patch('tickets.views.HTML')
    def test_manager_and_superuser_can_export_other_users_ticket(self, renderer):
        manager = User.objects.create_user(username='gerente_pdf')
        assign_role(manager, 'gerente')
        administrator = User.objects.create_superuser(
            username='admin_pdf', email='', password='test-only-password',
        )
        renderer.return_value.write_pdf.return_value = b'%PDF-test'
        for user in (manager, administrator):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertEqual(renderer.call_count, 2)

    def test_generates_real_pdf_without_optional_relations(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertIn('ticket_pdf001_completo.pdf', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    @patch('tickets.views.HTML')
    def test_report_contains_all_sections_and_does_not_update_budget(self, renderer):
        client = Cliente.objects.create(nome_razao_social='Cliente PDF', cpf_cnpj='12345678901')
        self.ticket.cliente = client
        self.ticket.nfe_path = 'nfe/nota-teste.pdf'
        self.ticket.save()
        budget = Orcamento.objects.create(ticket_orcamento=self.ticket, orcamento='Orçamento PDF', descricao='Escopo especial', valor_total=Decimal('999'))
        supply = Insumos.objects.create(insumo='Peça teste', tipo='M', unidade='UN', valor_unit=Decimal('12.50'))
        ItemOrcamento.objects.create(orcamento=budget, item=supply, quant=Decimal('2.50'))
        # Insumos removidos e valores financeiros vazios não impedem a exportação.
        ItemOrcamento.objects.create(orcamento=budget, item=None)
        Pagamentos.objects.create(ticket_pagamento=self.ticket, tipo='M', valor_pagamento=Decimal('10'), data_pagamento=date(2026, 10, 3), status_pagamento=True, comprovante='comprovantes/pago.pdf')
        Pagamentos.objects.create(ticket_pagamento=self.ticket, tipo='T', valor_pagamento=None, data_pagamento=date(2026, 10, 3))
        Recebimentos.objects.create(ticket_recebimento=self.ticket, valor_recebimento=Decimal('50'), status_recebimento=True, numero_nota_fiscal='NF-123', descricao_recebimento='Recebimento teste')
        HistoricoTicket.objects.create(ticket_historico=self.ticket, descricao_historico='Histórico teste <script>alert(1)</script>')
        Anexo.objects.create(ticket_anexo=self.ticket, arquivo='anexos/documento.pdf', descricao_anexo='Anexo teste')
        renderer.return_value.write_pdf.return_value = b'%PDF-test'
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = renderer.call_args.kwargs['string']
        for text in ['Descrição completa', 'Cliente PDF', 'Escopo especial', 'Peça teste', '31,25', '10,00', '50,00', 'NF-123', 'Histórico teste', 'Anexo teste', 'anexos/documento.pdf', 'nfe/nota-teste.pdf', 'comprovantes/pago.pdf', 'Insumo removido']:
            self.assertIn(text, html)
        self.assertIn('data:image/png;base64,', html)
        self.assertIn('Assinatura do responsável pela operação', html)
        self.assertIn('Operador Responsável', html)
        self.assertNotIn('<script>', html)
        from weasyprint import HTML
        self.assertTrue(HTML(string=html).write_pdf().startswith(b'%PDF-'))
        budget.refresh_from_db()
        self.assertEqual(budget.valor_total, Decimal('999'))
        context = ticket_report(self.ticket)
        self.assertEqual(context['summary'][0][1], 'R$ 31,25')
        self.assertEqual(context['summary'][1][1], 'R$ 10,00')


class TicketReportFinancialTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='financeiro_pdf')
        self.ticket = Ticket.objects.create(
            ticket='FINPDF001', usuario=self.user, descricao='Ticket financeiro',
        )

    def financial_entries(self):
        financial_fields = (
            'valor_material', 'valor_mao_obra', 'valor_custo',
            'valor_faturamento', 'valor_equipamento',
        )
        for field in financial_fields:
            setattr(self.ticket, field, Decimal('999.00'))
        self.ticket.save(update_fields=financial_fields)

        budgets = [
            Orcamento.objects.create(
                ticket_orcamento=self.ticket, orcamento='Orçamento principal',
                descricao='Materiais e execução', valor_total=Decimal('999.00'),
            ),
            Orcamento.objects.create(
                ticket_orcamento=self.ticket, orcamento='Orçamento complementar',
                descricao='Serviço e taxa', valor_total=Decimal('888.00'),
            ),
        ]
        for budget, kind, price, quantity in (
            (budgets[0], 'M', '12.50', '2.50'),
            (budgets[0], 'O', '40.00', '1.50'),
            (budgets[0], 'E', '25.00', '2.00'),
            (budgets[1], 'S', '80.00', '1.25'),
            (budgets[1], 'T', '9.00', '2.00'),
        ):
            supply = Insumos.objects.create(
                insumo=f'Insumo {kind}', tipo=kind, unidade='UN',
                valor_unit=Decimal(price),
            )
            ItemOrcamento.objects.create(
                orcamento=budget, item=supply, quant=Decimal(quantity),
            )

        for kind, amount, paid in (
            ('M', '10.00', True), ('M', '5.00', False),
            ('O', '7.50', True), ('O', '2.50', False),
            ('E', '4.00', True), ('E', '1.00', False),
            ('S', '20.00', False), ('T', '3.00', True),
            ('M', None, False),
        ):
            Pagamentos.objects.create(
                ticket_pagamento=self.ticket, tipo=kind,
                valor_pagamento=Decimal(amount) if amount is not None else None,
                data_pagamento=date(2026, 10, 3), status_pagamento=paid,
            )
        return budgets, financial_fields

    def test_report_uses_current_expenses_and_all_budget_items_without_saving(self):
        budgets, financial_fields = self.financial_entries()

        context = ticket_report(self.ticket)
        fields = dict(context['ticket_fields'])
        expected = {
            'Valor material': 'R$ 15,00',
            'Valor de mão de obra': 'R$ 10,00',
            'Valor de equipamento': 'R$ 5,00',
            'Valor de custo': 'R$ 53,00',
            'Valor de faturamento': 'R$ 259,25',
        }
        for label, value in expected.items():
            with self.subTest(label=label):
                self.assertEqual(fields[label], value)
        summary = dict(context['summary'])
        self.assertEqual(summary['Total dos itens orçados'], 'R$ 259,25')
        self.assertEqual(summary['Pagamentos realizados'], 'R$ 24,50')
        self.assertEqual(summary['Pagamentos pendentes'], 'R$ 28,50')
        self.assertEqual(summary['Saldo do orçamento após pagamentos'], 'R$ 206,25')

        for budget_context, expected_total in zip(context['budgets'], ('R$ 141,25', 'R$ 118,00')):
            self.assertEqual(dict(budget_context['fields'])['Valor total'], expected_total)
            self.assertEqual(budget_context['total'], expected_total)
        for field in financial_fields:
            self.assertEqual(getattr(self.ticket, field), Decimal('999.00'))
        self.ticket.refresh_from_db()
        for field in financial_fields:
            self.assertEqual(getattr(self.ticket, field), Decimal('999.00'))
        for budget, stored_total in zip(budgets, (Decimal('999.00'), Decimal('888.00'))):
            self.assertEqual(budget.valor_total, stored_total)
            budget.refresh_from_db()
            self.assertEqual(budget.valor_total, stored_total)

    def test_report_without_entries_ignores_default_revenue(self):
        self.assertEqual(self.ticket.valor_faturamento, 1)

        context = ticket_report(self.ticket)
        fields = dict(context['ticket_fields'])
        for label in (
            'Valor material', 'Valor de mão de obra', 'Valor de equipamento',
            'Valor de custo', 'Valor de faturamento',
        ):
            with self.subTest(label=label):
                self.assertEqual(fields[label], 'R$ 0,00')
        self.assertEqual(context['budgets'], [])
        self.assertTrue(all(value == 'R$ 0,00' for label, value in context['summary']))
        self.assertEqual(self.ticket.valor_faturamento, 1)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.valor_faturamento, Decimal('1.00'))

    def test_empty_budget_displays_zero_without_updating_stored_total(self):
        budget = Orcamento.objects.create(
            ticket_orcamento=self.ticket, orcamento='Orçamento vazio',
            descricao='Sem itens', valor_total=Decimal('321.00'),
        )

        context = ticket_report(self.ticket)

        self.assertEqual(dict(context['ticket_fields'])['Valor de faturamento'], 'R$ 0,00')
        self.assertEqual(context['budgets'][0]['items'], [])
        self.assertEqual(context['budgets'][0]['total'], 'R$ 0,00')
        self.assertEqual(dict(context['budgets'][0]['fields'])['Valor total'], 'R$ 0,00')
        self.assertEqual(budget.valor_total, Decimal('321.00'))
        budget.refresh_from_db()
        self.assertEqual(budget.valor_total, Decimal('321.00'))

    @patch('tickets.views.HTML')
    def test_pdf_renders_calculated_financial_values(self, renderer):
        self.financial_entries()
        renderer.return_value.write_pdf.return_value = b'%PDF-test'
        self.client.force_login(self.user)

        response = self.client.get(reverse('gerar_pdf_ticket', kwargs={'key': self.ticket.key}))

        self.assertEqual(response.status_code, 200)
        html = renderer.call_args.kwargs['string']
        ticket_section = html.split('<h2>Informações do ticket</h2>', 1)[1].split('<h2>Cliente</h2>', 1)[0]
        for label, value in (
            ('Valor material', 'R$ 15,00'),
            ('Valor de mão de obra', 'R$ 10,00'),
            ('Valor de equipamento', 'R$ 5,00'),
            ('Valor de custo', 'R$ 53,00'),
            ('Valor de faturamento', 'R$ 259,25'),
            ('Valor total', 'R$ 141,25'),
            ('Valor total', 'R$ 118,00'),
        ):
            with self.subTest(label=label, value=value):
                section = html if label == 'Valor total' else ticket_section
                self.assertInHTML(f'<tr><th>{label}</th><td>{value}</td></tr>', section)
        self.assertNotIn('R$ 999,00', html)
        self.assertNotIn('R$ 888,00', html)
