from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from rolepermissions.roles import assign_role

from clientes.models import Cliente
from colaborador.models import Colaborador
from tickets.models import Orcamento, Pagamentos, Recebimentos, Ticket

from .models import Empresa


@override_settings(TIME_ZONE='America/Sao_Paulo')
class DashboardTests(TestCase):
    """Os indicadores devem representar somente os tickets autorizados."""

    now = datetime(2026, 10, 3, 12, tzinfo=ZoneInfo('America/Sao_Paulo'))

    @classmethod
    def setUpTestData(cls):
        cls.company = Empresa.objects.create(
            nome_fantasia='Empresa de teste',
            razao_social='Empresa de teste LTDA',
            cnpj='12.345.678/0001-90',
            email='empresa@example.com',
            telefone='(11) 99999-9999',
            cep='01000-000',
            endereco='Rua de teste',
            numero='10',
            bairro='Centro',
            cidade='São Paulo',
            estado='SP',
        )
        cls.operator = User.objects.create_user(
            username='operadora', first_name='Ana', last_name='Operadora'
        )
        cls.other_operator = User.objects.create_user(
            username='externo', first_name='Bruno', last_name='Externo'
        )
        cls.manager = User.objects.create_user(username='gerente')
        assign_role(cls.manager, 'gerente')
        cls.admin = User.objects.create_superuser(
            username='administrador', email='admin@example.com', password='test-only-password'
        )
        cls.customer = Cliente.objects.create(
            nome_razao_social='Cliente próprio', cpf_cnpj='11111111111'
        )
        cls.other_customer = Cliente.objects.create(
            nome_razao_social='Cliente externo', cpf_cnpj='22222222222'
        )
        cls.collaborator = Colaborador.objects.create(nome_completo='Prestador próprio')
        cls.other_collaborator = Colaborador.objects.create(nome_completo='Prestador externo')

    def setUp(self):
        self.sequence = 0
        self.url = reverse('dashboard')

    def ticket(self, **kwargs):
        self.sequence += 1
        defaults = {
            'ticket': f'T{self.sequence:06d}',
            'usuario': self.operator,
            'cliente': self.customer,
            'colaborador': self.collaborator,
            'descricao': 'Serviço de teste',
        }
        defaults.update(kwargs)
        created_at = defaults.pop('created_at', self.now)
        ticket = Ticket.objects.create(**defaults)
        Ticket.objects.filter(pk=ticket.pk).update(data_criacao=created_at)
        return ticket

    def budget(self, ticket, value, created_at=None):
        budget = Orcamento.objects.create(
            ticket_orcamento=ticket,
            orcamento='Orçamento de teste',
            descricao='Escopo de teste',
            valor_total=Decimal(value),
        )
        Orcamento.objects.filter(pk=budget.pk).update(data_criacao=created_at or self.now)
        return budget

    def payment(self, ticket, value, paid):
        return Pagamentos.objects.create(
            ticket_pagamento=ticket,
            tipo='S',
            valor_pagamento=Decimal(value) if value is not None else None,
            data_pagamento=date(2026, 10, 3),
            status_pagamento=paid,
        )

    def receipt(self, ticket, value, received):
        return Recebimentos.objects.create(
            ticket_recebimento=ticket,
            valor_recebimento=Decimal(value) if value is not None else None,
            status_recebimento=received,
        )

    def dashboard(self, user=None):
        self.client.force_login(user or self.operator)
        with patch('core.views.timezone.now', return_value=self.now):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
        self.assertIn('next=/dashboard/', response.url)

    def test_requires_company_registration(self):
        Empresa.objects.all().delete()
        self.client.force_login(self.operator)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('empresa_cadastrar'), fetch_redirect_response=False)

    def test_empty_dashboard_has_zero_metrics_and_complete_empty_chart_series(self):
        response = self.dashboard()
        self.assertTrue(response.context['dashboard_metrics'])
        for key, value in response.context['dashboard_metrics'].items():
            with self.subTest(metric=key):
                self.assertEqual(value, 0)
        charts = response.context['dashboard_charts']
        self.assertEqual(sum(item['value'] for item in charts['status']), 0)
        self.assertEqual(len(charts['monthly']), 6)
        self.assertEqual([item['tickets'] for item in charts['monthly']], [0] * 6)
        self.assertEqual([item['budget'] for item in charts['monthly']], [0] * 6)
        self.assertEqual(len(charts['histogram']), 5)
        self.assertEqual([item['value'] for item in charts['histogram']], [0] * 5)
        for key in ('operators', 'clients', 'collaborators'):
            self.assertEqual(charts[key], [])

    def test_operator_scope_applies_to_table_metrics_and_every_chart(self):
        own_active = self.ticket(status='E', emergencial=True)
        own_final = self.ticket(status='F')
        other = self.ticket(
            usuario=self.other_operator,
            cliente=self.other_customer,
            colaborador=self.other_collaborator,
            status='R',
        )
        self.budget(own_active, '1000')
        self.budget(own_final, '500')
        self.budget(other, '99000')
        self.payment(other, '70000', True)
        self.receipt(other, '80000', True)
        response = self.dashboard()
        self.assertEqual(
            {ticket.pk for ticket in response.context['tickets']},
            {own_active.pk, own_final.pk},
        )
        metrics = response.context['dashboard_metrics']
        for key, value in {
            'tickets_total': 2, 'active': 1, 'finalized': 1, 'emergency': 1,
            'budget_total': Decimal('1500'), 'budget_month': Decimal('1500'),
            'paid_total': 0, 'received_total': 0,
            'operators_count': 1, 'clients_count': 1, 'collaborators_count': 1,
        }.items():
            with self.subTest(metric=key):
                self.assertEqual(metrics[key], value)
        charts = response.context['dashboard_charts']
        self.assertEqual(sum(item['value'] for item in charts['status']), 2)
        self.assertEqual(sum(item['tickets'] for item in charts['monthly']), 2)
        self.assertEqual(sum(item['budget'] for item in charts['monthly']), 1500)
        self.assertEqual([item['value'] for item in charts['histogram']], [2, 0, 0, 0, 0])
        for key in ('operators', 'clients', 'collaborators'):
            self.assertEqual([item['value'] for item in charts[key]], [2])
        self.assertNotIn('Bruno Externo', str(charts))
        self.assertNotIn('Cliente externo', str(charts))
        self.assertNotIn('Prestador externo', str(charts))

    def test_manager_and_superuser_see_all_tickets_including_missing_relations(self):
        own = self.ticket()
        other = self.ticket(
            usuario=self.other_operator,
            cliente=self.other_customer,
            colaborador=self.other_collaborator,
        )
        unassigned = self.ticket(usuario=None, cliente=None, colaborador=None)
        self.budget(other, '2000')
        for user in (self.manager, self.admin):
            with self.subTest(user=user.username):
                response = self.dashboard(user)
                self.assertEqual(
                    {ticket.pk for ticket in response.context['tickets']},
                    {own.pk, other.pk, unassigned.pk},
                )
                metrics = response.context['dashboard_metrics']
                self.assertEqual(metrics['tickets_total'], 3)
                self.assertEqual(metrics['budget_total'], Decimal('2000'))
                for key in ('operators_count', 'clients_count', 'collaborators_count'):
                    self.assertEqual(metrics[key], 2)
                self.assertIn('Cliente externo', str(response.context['dashboard_charts']))

    def test_client_and_collaborator_roles_keep_own_scope_even_with_linked_collaborator(self):
        for role in ('cliente', 'colaborador'):
            with self.subTest(role=role):
                user = User.objects.create_user(username=f'conta_{role}', first_name=f'Conta {role}')
                assign_role(user, role)
                linked_collaborator = Colaborador.objects.create(
                    user=user, nome_completo=f'Prestador da conta {role}'
                )
                own = self.ticket(usuario=user, colaborador=linked_collaborator)
                other = self.ticket(
                    usuario=self.other_operator,
                    cliente=self.other_customer,
                    colaborador=linked_collaborator,
                    status='F',
                    emergencial=True,
                )
                self.budget(own, '500')
                self.budget(other, '40000')
                self.payment(other, '20000', True)
                self.receipt(other, '30000', True)
                response = self.dashboard(user)
                self.assertEqual([ticket.pk for ticket in response.context['tickets']], [own.pk])
                metrics = response.context['dashboard_metrics']
                for key, value in {
                    'tickets_total': 1, 'active': 1, 'finalized': 0, 'emergency': 0,
                    'budget_total': Decimal('500'), 'budget_month': Decimal('500'),
                    'paid_total': 0, 'received_total': 0,
                    'operators_count': 1, 'clients_count': 1, 'collaborators_count': 1,
                }.items():
                    self.assertEqual(metrics[key], value, msg=f'{role}: {key}')
                charts = response.context['dashboard_charts']
                self.assertEqual(sum(item['value'] for item in charts['status']), 1)
                self.assertEqual(sum(item['tickets'] for item in charts['monthly']), 1)
                self.assertEqual(sum(item['budget'] for item in charts['monthly']), 500)
                self.assertEqual([item['value'] for item in charts['histogram']], [1, 0, 0, 0, 0])
                for key in ('operators', 'clients', 'collaborators'):
                    self.assertEqual([item['value'] for item in charts[key]], [1])
                self.assertNotIn('Bruno Externo', str(charts))
                self.assertNotIn('Cliente externo', str(charts))
                self.assertNotContains(response, f'#{other.ticket}')

    def test_empty_dashboard_actions_follow_each_role_create_permission(self):
        for role, can_create in (('cliente', True), ('operador', True), ('colaborador', False)):
            with self.subTest(role=role):
                user = User.objects.create_user(username=f'acao_{role}')
                assign_role(user, role)
                response = self.dashboard(user)
                self.assertEqual(response.context['dashboard_metrics']['tickets_total'], 0)
                self.assertFalse(response.context['dashboard_can_view_all'])
                if can_create:
                    self.assertContains(response, 'Novo ticket')
                    self.assertContains(response, reverse('cadastro-ticket'))
                    self.assertContains(response, 'Criar primeiro ticket')
                else:
                    self.assertContains(response, 'Ver tickets')
                    self.assertContains(response, 'Seus tickets aparecerão aqui')
                    self.assertNotContains(response, reverse('cadastro-ticket'))
                    self.assertNotContains(response, 'Criar primeiro ticket')

    def test_financial_totals_are_exact_without_join_multiplication_and_allow_nulls(self):
        first = self.ticket(status='E')
        second = self.ticket(status='E')
        self.budget(first, '1000.25')
        self.budget(first, '2000.10')
        self.budget(second, '499.65')
        self.payment(first, '125.30', True)
        self.payment(first, '99.99', False)
        self.payment(first, None, True)
        self.payment(second, '74.70', True)
        self.payment(second, '25.01', False)
        self.payment(second, None, False)
        self.receipt(first, '750.15', True)
        self.receipt(first, '400', False)
        self.receipt(first, None, True)
        self.receipt(second, '49.85', True)
        self.receipt(second, '100', False)
        self.receipt(second, None, False)
        response = self.dashboard()
        metrics = response.context['dashboard_metrics']
        expected = {
            'tickets_total': 2, 'active': 2,
            'budget_total': Decimal('3500.00'), 'budget_month': Decimal('3500.00'),
            'paid_total': Decimal('200.00'), 'pending_payments': Decimal('125.00'),
            'received_total': Decimal('800.00'), 'receivable_total': Decimal('500.00'),
            'operators_count': 1, 'clients_count': 1, 'collaborators_count': 1,
        }
        for key, value in expected.items():
            with self.subTest(metric=key):
                self.assertEqual(metrics[key], value)
        by_id = {ticket.pk: ticket for ticket in response.context['tickets']}
        self.assertEqual(by_id[first.pk].total_orcamentos, Decimal('3000.35'))
        self.assertEqual(by_id[second.pk].total_orcamentos, Decimal('499.65'))
        self.assertEqual(by_id[first.pk].total_pagamentos, Decimal('225.29'))
        self.assertEqual(by_id[second.pk].total_pagamentos, Decimal('99.71'))
        charts = response.context['dashboard_charts']
        self.assertEqual(sum(item['tickets'] for item in charts['monthly']), 2)
        self.assertEqual(sum(item['budget'] for item in charts['monthly']), 3500)
        for key in ('operators', 'clients', 'collaborators'):
            self.assertEqual([item['value'] for item in charts[key]], [2])

    def test_active_and_status_counts_include_all_valid_statuses_once(self):
        for index, (key, _) in enumerate(Ticket.STATUS_CHOICES):
            self.ticket(status=key, emergencial=index < 3)
        response = self.dashboard()
        metrics = response.context['dashboard_metrics']
        self.assertEqual(metrics['tickets_total'], 8)
        self.assertEqual(metrics['active'], 6)
        self.assertEqual(metrics['finalized'], 1)
        self.assertEqual(metrics['emergency'], 3)
        statuses = response.context['dashboard_charts']['status']
        self.assertEqual({item['key']: item['value'] for item in statuses},
                         {key: 1 for key, _ in Ticket.STATUS_CHOICES})

    def test_monthly_series_is_chronological_fills_empty_months_and_uses_local_timezone(self):
        # 02:59 UTC ainda pertence ao mês anterior em São Paulo.
        dated_values = [
            (datetime(2026, 5, 1, 2, 59, tzinfo=datetime_timezone.utc), '9000'),
            (datetime(2026, 5, 1, 3, 0, tzinfo=datetime_timezone.utc), '100'),
            (datetime(2026, 8, 15, 12, tzinfo=datetime_timezone.utc), '200'),
            (datetime(2026, 10, 1, 2, 59, tzinfo=datetime_timezone.utc), '300'),
            (datetime(2026, 10, 1, 3, 0, tzinfo=datetime_timezone.utc), '400'),
            (datetime(2026, 11, 1, 3, 0, tzinfo=datetime_timezone.utc), '8000'),
        ]
        for created_at, value in dated_values:
            ticket = self.ticket(created_at=created_at)
            self.budget(ticket, value, created_at=created_at)
        response = self.dashboard()
        series = response.context['dashboard_charts']['monthly']
        self.assertEqual(len(series), 6)
        self.assertEqual(len({item['label'] for item in series}), 6)
        self.assertEqual([item['tickets'] for item in series], [1, 0, 0, 1, 1, 1])
        self.assertEqual([item['budget'] for item in series], [100, 0, 0, 200, 300, 400])
        self.assertEqual(response.context['dashboard_metrics']['budget_month'], Decimal('400'))

    def test_histogram_uses_sum_per_ticket_and_inclusive_upper_boundaries(self):
        values = ['-1', '0', '0.01', '1000', '1000.01', '5000',
                  '5000.01', '10000', '10000.01', '25000', '25000.01']
        for value in values:
            ticket = self.ticket()
            if value == '1000':
                self.budget(ticket, '600')
                self.budget(ticket, '400')
            elif value == '5000':
                self.budget(ticket, '3000')
                self.budget(ticket, '2000')
            else:
                self.budget(ticket, value)
        self.ticket()  # Sem orçamento, deve ficar fora das faixas positivas.
        response = self.dashboard()
        histogram = response.context['dashboard_charts']['histogram']
        self.assertEqual(len(histogram), 5)
        self.assertEqual([item['value'] for item in histogram], [2, 2, 2, 2, 1])
        self.assertEqual(response.context['dashboard_metrics']['tickets_total'], 12)

    def test_rankings_limit_top_five_and_count_tickets_per_distinct_participant(self):
        for index, count in enumerate(range(7, 0, -1)):
            operator = User.objects.create_user(username=f'ranking{index}', first_name=f'Operador {index}')
            customer = Cliente.objects.create(nome_razao_social=f'Cliente {index}', cpf_cnpj=f'333333333{index:02d}')
            collaborator = Colaborador.objects.create(nome_completo=f'Prestador {index}')
            for _ in range(count):
                self.ticket(usuario=operator, cliente=customer, colaborador=collaborator)
        response = self.dashboard(self.manager)
        metrics = response.context['dashboard_metrics']
        self.assertEqual(metrics['tickets_total'], 28)
        for key in ('operators_count', 'clients_count', 'collaborators_count'):
            self.assertEqual(metrics[key], 7)
        charts = response.context['dashboard_charts']
        for key, prefix in (('operators', 'Operador'), ('clients', 'Cliente'), ('collaborators', 'Prestador')):
            with self.subTest(ranking=key):
                self.assertEqual([item['value'] for item in charts[key]], [7, 6, 5, 4, 3])
                self.assertEqual([item['label'] for item in charts[key]],
                                 [f'{prefix} {index}' for index in range(5)])
