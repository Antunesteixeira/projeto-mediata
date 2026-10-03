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
