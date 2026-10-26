from datetime import datetime, timedelta
from decimal import Decimal
import re
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from rolepermissions.roles import assign_role

from clientes.models import Cliente
from colaborador.models import Colaborador
from tickets.models import Orcamento, Pagamentos, Ticket
from core.models import Empresa
from usuarios.models import UsuarioEmpresa


@override_settings(TIME_ZONE='America/Sao_Paulo')
class PaymentReportFilterTests(TestCase):
    now = datetime(2026, 10, 3, 12, tzinfo=ZoneInfo('America/Sao_Paulo'))

    @classmethod
    def setUpTestData(cls):
        cls.company = Empresa.objects.create(
            nome_fantasia='Empresa A do relatório', razao_social='Empresa A de teste',
            cnpj='11.111.111/0001-11', email='empresa-a@example.com', telefone='(11) 1111-1111',
        )
        cls.foreign_company = Empresa.objects.create(
            nome_fantasia='Empresa B do relatório', razao_social='Empresa B de teste',
            cnpj='22.222.222/0001-22', email='empresa-b@example.com', telefone='(22) 2222-2222',
        )
        cls.operator = User.objects.create_user(username='operador_relatorio')
        assign_role(cls.operator, 'operador')
        cls.other_operator = User.objects.create_user(username='outro_operador_relatorio')
        assign_role(cls.other_operator, 'operador')
        cls.manager = User.objects.create_user(username='gerente_relatorio')
        assign_role(cls.manager, 'gerente')
        cls.admin = User.objects.create_superuser(
            username='admin_relatorio', email='admin@example.com', password='test-password'
        )
        cls.foreign_operator = User.objects.create_user(username='operador_empresa_b')
        assign_role(cls.foreign_operator, 'operador')
        cls.foreign_manager = User.objects.create_user(username='gerente_empresa_b')
        assign_role(cls.foreign_manager, 'gerente')
        for user in (cls.operator, cls.other_operator, cls.manager):
            UsuarioEmpresa.objects.create(usuario=user, empresa=cls.company)
        UsuarioEmpresa.objects.create(usuario=cls.foreign_operator, empresa=cls.foreign_company)
        UsuarioEmpresa.objects.create(usuario=cls.foreign_manager, empresa=cls.foreign_company)
        cls.customer = Cliente.objects.create(
            nome_razao_social='Cliente do relatório', cpf_cnpj='11111111111', empresa=cls.company,
        )
        cls.other_customer = Cliente.objects.create(
            nome_razao_social='Outro cliente', cpf_cnpj='22222222222', empresa=cls.company,
        )
        cls.foreign_customer = Cliente.objects.create(
            nome_razao_social='Cliente da empresa B', cpf_cnpj='33333333333', empresa=cls.foreign_company,
        )
        cls.collaborator = Colaborador.objects.create(nome_completo='Prestador do relatório', empresa=cls.company)
        cls.other_collaborator = Colaborador.objects.create(nome_completo='Outro prestador', empresa=cls.company)
        cls.foreign_collaborator = Colaborador.objects.create(
            nome_completo='Prestador da empresa B', empresa=cls.foreign_company,
        )

    def setUp(self):
        self.sequence = 0
        self.url = reverse('relatorios')

    def ticket(self, **kwargs):
        self.sequence += 1
        values = {
            'ticket': f'REL{self.sequence:06d}',
            'usuario': self.operator,
            'empresa': self.company,
            'cliente': self.customer,
            'colaborador': self.collaborator,
            'status': 'A',
            'descricao': 'Serviço de teste',
        }
        values.update(kwargs)
        created_at = values.pop('created_at', self.now)
        ticket = Ticket.objects.create(**values)
        Ticket.objects.filter(pk=ticket.pk).update(data_criacao=created_at)
        return ticket

    def payment(self, ticket, value='100.00', paid=False, kind='S', payment_date=None):
        return Pagamentos.objects.create(
            ticket_pagamento=ticket,
            tipo=kind,
            valor_pagamento=Decimal(value) if value is not None else None,
            data_pagamento=payment_date or self.now.date(),
            status_pagamento=paid,
        )

    def budget(self, ticket, value):
        budget = Orcamento.objects.create(
            ticket_orcamento=ticket,
            orcamento='Orçamento de teste',
            descricao='Escopo de teste',
            valor_total=Decimal(value),
        )
        Orcamento.objects.filter(pk=budget.pk).update(data_criacao=self.now)
        return budget

    def report(self, filters=None, user=None, method='get'):
        self.client.force_login(user or self.manager)
        data = {'date_range': '365'}
        data.update(filters or {})
        with patch('relatorios.views.now', return_value=self.now):
            response = getattr(self.client, method)(self.url, data)
        self.assertEqual(response.status_code, 200)
        return response

    def assert_tickets(self, response, tickets):
        self.assertEqual(
            {ticket.pk for ticket in response.context['tickets']},
            {ticket.pk for ticket in tickets},
        )

    def tickets_for_all_statuses(self):
        tickets = {}
        for status, _ in Ticket.STATUS_CHOICES:
            ticket = self.ticket(status=status)
            self.payment(ticket, '10.00', paid=False)
            self.payment(ticket, '20.00', paid=True)
            self.budget(ticket, '100.00')
            tickets[status] = ticket
        return tickets

    def test_pending_limits_ticket_statuses_for_get_and_post(self):
        tickets = self.tickets_for_all_statuses()
        without_pending = self.ticket(status='A')
        self.payment(without_pending, paid=True)
        for method in ('get', 'post'):
            with self.subTest(method=method):
                response = self.report({'status_pagamento': ['False']}, method=method)
                self.assert_tickets(response, [tickets[status] for status in ('A', 'E', 'X', 'V')])
                self.assertEqual(response.context['total_pendentes'], Decimal('40.00'))
                self.assertEqual(response.context['total_pagos'], 0)
                self.assertEqual(response.context['total_pagamentos'], Decimal('40.00'))
                self.assertEqual(response.context['orcamento_total'], Decimal('400.00'))
                self.assertEqual(response.context['filtro_status_pagamento_list'], ['False'])

    def test_selecting_paid_and_pending_still_limits_ticket_statuses(self):
        tickets = self.tickets_for_all_statuses()
        paid_only = self.ticket(status='A')
        self.payment(paid_only, '35.00', paid=True)
        response = self.report({'status_pagamento': ['True', 'False']})
        expected = [tickets[status] for status in ('A', 'E', 'X', 'V')] + [paid_only]
        self.assert_tickets(response, expected)
        self.assertEqual(response.context['total_pagos'], Decimal('115.00'))
        self.assertEqual(response.context['total_pendentes'], Decimal('40.00'))
        self.assertEqual(response.context['total_pagamentos'], Decimal('155.00'))

    def test_paid_alone_preserves_all_ticket_statuses(self):
        tickets = self.tickets_for_all_statuses()
        response = self.report({'status_pagamento': ['True']})
        self.assert_tickets(response, tickets.values())
        self.assertEqual(response.context['total_pagos'], Decimal('160.00'))
        self.assertEqual(response.context['total_pendentes'], 0)
        self.assertEqual(response.context['total_pagamentos'], Decimal('160.00'))

    def test_without_payment_status_filter_preserves_all_tickets(self):
        tickets = self.tickets_for_all_statuses()
        without_payments = self.ticket(status='F')
        response = self.report()
        self.assert_tickets(response, [*tickets.values(), without_payments])
        self.assertEqual(response.context['total_pagos'], Decimal('160.00'))
        self.assertEqual(response.context['total_pendentes'], Decimal('80.00'))
        self.assertEqual(response.context['total_pagamentos'], Decimal('240.00'))

    def test_pending_totals_include_only_selected_payment_type_and_status(self):
        ticket = self.ticket(status='E')
        self.budget(ticket, '1000.00')
        selected = self.payment(ticket, '125.30', kind='M')
        self.payment(ticket, '10.20', kind='S')
        self.payment(ticket, '99.99', paid=True, kind='M')
        for kind, amount in (('M', '125.30'), ('S', '10.20')):
            with self.subTest(kind=kind):
                response = self.report({'pagamentos': kind, 'status_pagamento': ['False']})
                self.assert_tickets(response, [ticket])
                reported_ticket = list(response.context['tickets'])[0]
                self.assertEqual(reported_ticket.total_pagamentos, Decimal(amount))
                self.assertEqual(response.context['total_pagamentos'], Decimal(amount))
                self.assertEqual(response.context['total_pendentes'], Decimal(amount))
                self.assertEqual(response.context['total_pagos'], 0)
                self.assertEqual(response.context['total_lucros'], Decimal('1000.00') - Decimal(amount))
                if kind == 'M':
                    self.assertEqual([payment.pk for payment in reported_ticket.pagamentos_prefetch], [selected.pk])

    def test_payment_type_and_status_must_match_the_same_payment(self):
        different_payments = self.ticket(status='V')
        self.payment(different_payments, '100.00', paid=True, kind='M')
        self.payment(different_payments, '200.00', paid=False, kind='S')
        matching = self.ticket(status='X')
        self.payment(matching, '30.00', paid=False, kind='M')
        response = self.report({'pagamentos': 'M', 'status_pagamento': ['False']})
        self.assert_tickets(response, [matching])
        self.assertEqual(response.context['total_pendentes'], Decimal('30.00'))
        self.assertEqual(response.context['total_pagamentos'], Decimal('30.00'))

    def test_pending_intersects_explicit_ticket_status_selection(self):
        tickets = self.tickets_for_all_statuses()
        for statuses, expected in ((['F'], []), (['V'], [tickets['V']]), (['F', 'A'], [tickets['A']])):
            with self.subTest(statuses=statuses):
                response = self.report({'status': statuses, 'status_pagamento': ['False']})
                self.assert_tickets(response, expected)
                self.assertEqual(response.context['total_pendentes'], Decimal('10.00') * len(expected))

    def test_pending_filter_uses_the_company_team_and_manager_user_filter(self):
        own = self.ticket(status='A')
        other = self.ticket(status='V', usuario=self.other_operator)
        for ticket, value in ((own, '10.00'), (other, '100.00')):
            self.payment(ticket, value)
        response = self.report({'status_pagamento': ['False']})
        self.assert_tickets(response, [own, other])
        self.assertEqual(response.context['total_pendentes'], Decimal('110.00'))
        response = self.report({'status_pagamento': ['False']}, user=self.manager)
        self.assert_tickets(response, [own, other])
        self.assertEqual(response.context['total_pendentes'], Decimal('110.00'))
        response = self.report(
            {'status_pagamento': ['False'], 'usuario': str(self.other_operator.pk)}, user=self.manager
        )
        self.assert_tickets(response, [other])
        self.assertEqual(response.context['total_pendentes'], Decimal('100.00'))

    def test_superuser_without_manager_group_can_report_all_companies(self):
        own = self.ticket(status='A', usuario=self.admin)
        other = self.ticket(status='V')
        foreign = self.ticket(
            status='V', usuario=self.foreign_operator, empresa=self.foreign_company,
            cliente=self.foreign_customer, colaborador=self.foreign_collaborator,
        )
        self.payment(own, '10.00')
        self.payment(other, '100.00')
        self.payment(foreign, '1000.00')
        response = self.report({'status_pagamento': ['False']}, user=self.admin)
        self.assert_tickets(response, [own, other, foreign])
        self.assertEqual(response.context['total_pendentes'], Decimal('1110.00'))

    def test_pending_intersects_customer_and_collaborator_filters(self):
        matching = self.ticket(status='E')
        different_customer = self.ticket(status='A', cliente=self.other_customer)
        different_collaborator = self.ticket(status='V', colaborador=self.other_collaborator)
        wrong_status = self.ticket(status='F')
        for ticket in (matching, different_customer, different_collaborator, wrong_status):
            self.payment(ticket, '10.00')
        response = self.report({
            'cliente': str(self.customer.pk),
            'colaborador': str(self.collaborator.pk),
            'status_pagamento': ['False'],
        })
        self.assert_tickets(response, [matching])
        self.assertEqual(response.context['total_pendentes'], Decimal('10.00'))

    def test_period_filters_ticket_creation_and_preserves_matching_payment_dates(self):
        ticket = self.ticket(status='E')
        recent_payment = self.payment(ticket, '25.01')
        old_payment = self.payment(ticket, '999.00', payment_date=(self.now - timedelta(days=60)).date())
        older_ticket = self.ticket(status='A', created_at=self.now - timedelta(days=60))
        self.payment(older_ticket, '500.00')
        response = self.report({'date_range': '30', 'status_pagamento': ['False']})
        self.assert_tickets(response, [ticket])
        self.assertEqual(response.context['total_pendentes'], Decimal('1024.01'))
        self.assertEqual(
            {payment.pk for payment in list(response.context['tickets'])[0].pagamentos_prefetch},
            {recent_payment.pk, old_payment.pk},
        )

    def test_custom_period_preserves_ticket_creation_date_filter(self):
        ticket = self.ticket(status='E')
        self.payment(ticket, '12.34', payment_date=(self.now - timedelta(days=1)).date())
        self.payment(ticket, '800.00', payment_date=(self.now - timedelta(days=15)).date())
        response = self.report({
            'date_range': 'custom',
            'data_inicio': '2026-10-01',
            'data_fim': '2026-10-04',
            'status_pagamento': ['False'],
        })
        self.assert_tickets(response, [ticket])
        self.assertEqual(response.context['total_pendentes'], Decimal('812.34'))
        self.assertEqual(response.context['total_pagamentos'], Decimal('812.34'))

    def test_null_payment_amounts_are_zero_and_do_not_hide_valid_values(self):
        ticket = self.ticket(status='A', cliente=None, colaborador=None)
        self.payment(ticket, None, paid=False)
        self.payment(ticket, '125.30', paid=False)
        self.payment(ticket, None, paid=True)
        self.payment(ticket, '74.70', paid=True)
        for statuses, expected_paid, expected_pending in (
            (['False'], '0.00', '125.30'),
            (['True'], '74.70', '0.00'),
            (['True', 'False'], '74.70', '125.30'),
        ):
            with self.subTest(statuses=statuses):
                response = self.report({'status_pagamento': statuses})
                self.assert_tickets(response, [ticket])
                self.assertEqual(response.context['total_pagos'], Decimal(expected_paid))
                self.assertEqual(response.context['total_pendentes'], Decimal(expected_pending))
                self.assertEqual(
                    list(response.context['tickets'])[0].total_pagamentos,
                    Decimal(expected_paid) + Decimal(expected_pending),
                )

    def test_payment_categories_sum_amounts_exactly_without_mixing_services(self):
        ticket = self.ticket()
        amounts = {
            'M': ('1234.50', '0.06', None),
            'O': ('300.10', '50.25', None),
            'E': ('25.05', '25.05', None),
            'T': ('3.33', '4.44', None),
            'S': ('9.99', None),
        }
        for kind, values in amounts.items():
            for index, value in enumerate(values):
                self.payment(ticket, value, kind=kind, paid=bool(index % 2))

        other_ticket = self.ticket(
            usuario=self.foreign_operator, empresa=self.foreign_company,
            cliente=self.foreign_customer, colaborador=self.foreign_collaborator,
        )
        self.payment(other_ticket, '9999.99', kind='M')
        response = self.report()
        self.assert_tickets(response, [ticket])
        reported_ticket = list(response.context['tickets'])[0]
        expected = {
            'M': Decimal('1234.56'),
            'O': Decimal('350.35'),
            'E': Decimal('50.10'),
            'T': Decimal('7.77'),
            'S': Decimal('9.99'),
        }
        self.assertEqual(reported_ticket.pagamentos_por_tipo, expected)
        self.assertEqual(reported_ticket.total_pagamentos, Decimal('1652.77'))
        self.assertEqual(response.context['total_pagamentos'], Decimal('1652.77'))
        for amount in reported_ticket.pagamentos_por_tipo.values():
            self.assertIsInstance(amount, Decimal)

    def test_payment_categories_follow_combined_type_and_pending_filters(self):
        ticket = self.ticket(status='E')
        pending_amounts = {'M': '11.11', 'O': '22.22', 'E': '33.33', 'T': '44.44', 'S': '55.55'}
        for kind, amount in pending_amounts.items():
            self.payment(ticket, amount, kind=kind)
            self.payment(ticket, '100.00', kind=kind, paid=True)
            self.payment(ticket, None, kind=kind)

        for selected_kind, amount in pending_amounts.items():
            with self.subTest(kind=selected_kind):
                response = self.report({
                    'pagamentos': selected_kind,
                    'status_pagamento': ['False'],
                })
                self.assert_tickets(response, [ticket])
                reported_ticket = list(response.context['tickets'])[0]
                self.assertEqual(
                    reported_ticket.pagamentos_por_tipo,
                    {
                        kind: Decimal(amount) if kind == selected_kind else Decimal('0')
                        for kind in pending_amounts
                    },
                )
                self.assertEqual(reported_ticket.total_pagamentos, Decimal(amount))
                self.assertEqual(response.context['total_pendentes'], Decimal(amount))
                self.assertEqual(response.context['total_pagos'], Decimal('0'))

    def test_payment_categories_follow_pending_filter_without_type_selection(self):
        ticket = self.ticket(status='V')
        expected = {}
        for index, kind in enumerate(('M', 'S', 'O', 'E', 'T'), start=1):
            amount = Decimal(index) + Decimal('0.15')
            self.payment(ticket, str(amount), kind=kind)
            self.payment(ticket, '50.00', kind=kind, paid=True)
            expected[kind] = amount
        excluded = self.ticket(status='F')
        self.payment(excluded, '1000.00', kind='M')

        response = self.report({'status_pagamento': ['False']})
        self.assert_tickets(response, [ticket])
        reported_ticket = list(response.context['tickets'])[0]
        self.assertEqual(reported_ticket.pagamentos_por_tipo, expected)
        self.assertEqual(reported_ticket.total_pagamentos, Decimal('15.75'))

    def test_ticket_without_payments_has_zero_in_every_payment_category(self):
        ticket = self.ticket()
        response = self.report()
        self.assert_tickets(response, [ticket])
        reported_ticket = list(response.context['tickets'])[0]
        self.assertEqual(
            reported_ticket.pagamentos_por_tipo,
            {kind: Decimal('0') for kind in ('M', 'S', 'O', 'E', 'T')},
        )
        self.assertEqual(reported_ticket.total_pagamentos, Decimal('0'))

    def test_report_renders_category_columns_and_amounts_in_the_correct_order(self):
        ticket = self.ticket()
        self.budget(ticket, '2000.00')
        for kind, value in (('M', '1234.56'), ('O', '234.56'), ('E', '34.56'), ('T', '4.56'), ('S', '1.00')):
            self.payment(ticket, value, kind=kind)
        response = self.report()
        table = response.content.decode().split('id="datatablesSimple"', 1)[1].split('</table>', 1)[0]
        headers = [
            re.sub(r'<[^>]+>', '', content).strip()
            for content in re.findall(r'<th\b[^>]*>(.*?)</th>', table, re.DOTALL)
        ]
        self.assertEqual(len(headers), 12)
        self.assertEqual(headers[6:], ['Orçamentos', 'Material', 'Mão de obra', 'Equipamentos', 'Taxas', 'Pagamentos'])
        cells = re.findall(r'<td\b([^>]*)>(.*?)</td>', table, re.DOTALL)
        self.assertEqual(len(cells), 12)
        for (attributes, content), raw_value, display_value in zip(
            cells[7:11],
            ('1234.56', '234.56', '34.56', '4.56'),
            ('R$ 1.234,56', 'R$ 234,56', 'R$ 34,56', 'R$ 4,56'),
        ):
            self.assertIn(f'data-order="{raw_value}"', attributes)
            self.assertEqual(' '.join(re.sub(r'<[^>]+>', '', content).split()), display_value)
        self.assertEqual(' '.join(re.sub(r'<[^>]+>', '', cells[11][1]).split()), 'R$ 1.509,24')

    def test_empty_report_spans_all_twelve_columns(self):
        response = self.report()
        self.assertContains(response, 'colspan="12"', count=1)
        self.assertContains(response, 'Nenhum ticket encontrado com os filtros aplicados')

    def test_company_reports_exclude_foreign_metrics_and_filter_choices(self):
        own = self.ticket()
        foreign = self.ticket(
            usuario=self.foreign_operator, empresa=self.foreign_company,
            cliente=self.foreign_customer, colaborador=self.foreign_collaborator,
        )
        self.budget(own, '100.00')
        self.payment(own, '10.00')
        self.budget(foreign, '9999.00')
        self.payment(foreign, '8888.00')
        for user in (self.manager,):
            with self.subTest(user=user.username):
                response = self.report(user=user)
                self.assert_tickets(response, [own])
                self.assertEqual(response.context['orcamento_total'], Decimal('100.00'))
                self.assertEqual(response.context['total_pagamentos'], Decimal('10.00'))
                self.assertNotIn(self.foreign_operator.pk, response.context['usuarios'].values_list('pk', flat=True))
                self.assertNotIn(self.foreign_customer.pk, response.context['clientes'].values_list('pk', flat=True))
                self.assertNotIn(self.foreign_collaborator.pk, response.context['colaboradores'].values_list('pk', flat=True))
                self.assertNotContains(response, self.foreign_customer.nome_razao_social)

    def test_manager_operator_filter_uses_claiming_user_for_subscriber_ticket(self):
        subscriber = User.objects.create_user(username='assinante_global_relatorio')
        assign_role(subscriber, 'assinante')
        ticket = self.ticket(usuario=subscriber, assumido_por=self.other_operator)
        self.payment(ticket, '12.50')
        response = self.report({'usuario': str(self.other_operator.pk)}, user=self.manager)
        self.assert_tickets(response, [ticket])
        self.assertEqual(response.context['total_pagamentos'], Decimal('12.50'))
        self.assertNotIn(subscriber.pk, response.context['usuarios'].values_list('pk', flat=True))

    def test_company_filters_reject_foreign_ids(self):
        self.client.force_login(self.manager)
        for name, value in (
            ('usuario', self.foreign_operator.pk), ('cliente', self.foreign_customer.pk),
            ('colaborador', self.foreign_collaborator.pk), ('cliente', 'not-an-id'),
        ):
            with self.subTest(name=name, value=value):
                response = self.client.get(self.url, {'date_range': '365', name: str(value)})
                self.assertEqual(response.status_code, 404)

    def test_non_operational_roles_and_missing_or_inactive_company_cannot_report(self):
        for role in ('operador', 'cliente', 'colaborador'):
            user = User.objects.create_user(username=f'{role}_bloqueado_relatorio')
            assign_role(user, role)
            UsuarioEmpresa.objects.create(usuario=user, empresa=self.company)
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        unlinked = User.objects.create_user(username='gerente_sem_empresa_relatorio')
        assign_role(unlinked, 'gerente')
        self.client.force_login(unlinked)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.foreign_company.ativo = False
        self.foreign_company.save(update_fields=['ativo'])
        self.client.force_login(self.foreign_manager)
        self.assertEqual(self.client.get(self.url).status_code, 403)
