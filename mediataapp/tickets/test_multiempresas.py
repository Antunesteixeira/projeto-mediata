from datetime import date
from decimal import Decimal
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rolepermissions.roles import assign_role

from clientes.models import Cliente
from colaborador.models import Colaborador
from insumos.models import Insumos
from usuarios.models import UsuarioEmpresa
from usuarios.test_helpers import criar_empresa, vincular_usuario
from .models import (
    Anexo, HistoricoTicket, ItemOrcamento, Orcamento, Pagamentos,
    Recebimentos, SequenciaTicket, Ticket,
)


class TicketMultiempresaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company_a = criar_empresa()
        cls.company_b = criar_empresa('Empresa fictícia B', '00.000.000/0000-02')
        cls.operator_a = User.objects.create_user(username='operador_empresa_a')
        cls.manager_a = User.objects.create_user(username='gerente_empresa_a')
        cls.operator_b = User.objects.create_user(username='operador_empresa_b')
        cls.manager_b = User.objects.create_user(username='gerente_empresa_b')
        for user, role, company in (
            (cls.operator_a, 'operador', cls.company_a),
            (cls.manager_a, 'gerente', cls.company_a),
            (cls.operator_b, 'operador', cls.company_b),
            (cls.manager_b, 'gerente', cls.company_b),
        ):
            assign_role(user, role)
            vincular_usuario(user, company)
        cls.subscriber = User.objects.create_user(username='autor_independente')
        assign_role(cls.subscriber, 'assinante')
        cls.subscriber_b = User.objects.create_user(username='outro_autor_independente')
        assign_role(cls.subscriber_b, 'assinante')
        cls.available = Ticket.objects.create(
            ticket='QUEUE001', usuario=cls.subscriber, status='L',
            descricao='Solicitação disponível para atendimento',
            nfe_path='nfe/SEGREDO-FILA.pdf',
        )
        cls.assigned_b = Ticket.objects.create(
            ticket='EMPB001', usuario=cls.subscriber_b, empresa=cls.company_b,
            assumido_por=cls.operator_b, status='L', descricao='Solicitação privada da empresa B',
        )
        cls.budget = Orcamento.objects.create(
            ticket_orcamento=cls.available, orcamento='ORCAMENTO-SEGREDO-FILA',
            descricao='Escopo financeiro privado', valor_total=Decimal('87654.32'),
        )
        cls.supply = Insumos.objects.create(
            empresa=cls.company_a, insumo='INSUMO-SEGREDO-FILA', codigo='INS001',
            tipo='M', unidade='UN', valor_unit=Decimal('33.33'),
        )
        cls.item = ItemOrcamento.objects.create(
            orcamento=cls.budget, item=cls.supply, quant=Decimal('2.00'),
        )
        cls.payment = Pagamentos.objects.create(
            ticket_pagamento=cls.available, tipo='M', valor_pagamento=Decimal('76543.21'),
            data_pagamento=date(2026, 10, 13), comprovante='comprovantes/SEGREDO-FILA.pdf',
        )
        cls.receipt = Recebimentos.objects.create(
            ticket_recebimento=cls.available, valor_recebimento=Decimal('65432.10'),
            descricao_recebimento='RECEBIMENTO-SEGREDO-FILA',
        )
        cls.attachment = Anexo.objects.create(
            ticket_anexo=cls.available, arquivo='anexos/SEGREDO-FILA.pdf',
        )

    def setUp(self):
        media = TemporaryDirectory(prefix='mediata-empresa-tests-')
        self.addCleanup(media.cleanup)
        configuration = override_settings(MEDIA_ROOT=media.name)
        configuration.enable()
        self.addCleanup(configuration.disable)
        self.media_root = Path(media.name)
        self.client.force_login(self.operator_a)

    def snapshot(self):
        models = (
            Ticket, SequenciaTicket, HistoricoTicket, Orcamento, ItemOrcamento,
            Pagamentos, Recebimentos, Anexo, Cliente, Colaborador, Insumos, UsuarioEmpresa,
        )
        return {
            model._meta.label_lower: list(model.objects.order_by('pk').values())
            for model in models
        }

    def url(self, name, ticket=None):
        return reverse(name, kwargs={'key': (ticket or self.available).key})

    def claim(self, user=None, **payload):
        if user is not None:
            self.client.force_login(user)
        return self.client.post(self.url('assumir-ticket'), payload)

    def claim_as_a(self):
        response = self.claim()
        self.assertEqual(response.status_code, 302)
        self.available.refresh_from_db()
        self.assertEqual(self.available.empresa_id, self.company_a.pk)
        return response

    def test_queue_and_claim_require_login(self):
        self.client.logout()
        for method, url in (
            ('get', reverse('tickets-disponiveis')),
            ('get', self.url('ticket-disponivel')),
            ('post', self.url('assumir-ticket')),
        ):
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response.url)

    def test_queue_contains_only_unclaimed_subscriber_tickets_in_levantamento(self):
        progressed = Ticket.objects.create(
            ticket='QUEUE002', usuario=self.subscriber, status='E', descricao='Fila já em execução',
        )
        internal = Ticket.objects.create(
            ticket='INTERNAL01', usuario=self.manager_a, descricao='Ticket interno não disponível',
        )
        before = self.snapshot()
        response = self.client.get(reverse('tickets-disponiveis'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.available.ticket)
        for ticket in (progressed, internal, self.assigned_b):
            self.assertNotContains(response, ticket.ticket)
            self.assertEqual(self.client.get(self.url('ticket-disponivel', ticket)).status_code, 404)
        self.assertEqual(self.snapshot(), before)

    def test_available_preview_is_read_only_and_hides_financials_and_documents(self):
        before = self.snapshot()
        response = self.client.get(self.url('ticket-disponivel'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.available.ticket)
        self.assertContains(response, self.available.descricao)
        for private_value in (
            self.budget.orcamento, self.supply.insumo, self.payment.comprovante,
            self.receipt.descricao_recebimento, self.attachment.arquivo.name,
            self.available.nfe_path, 'R$',
        ):
            self.assertNotContains(response, private_value)
        self.assertEqual(self.client.get(self.url('exibir-ticket')).status_code, 404)
        self.assertEqual(self.client.get(self.url('editar-ticket')).status_code, 404)
        self.assertEqual(self.client.get(self.url('gerar_pdf_ticket')).status_code, 403)
        self.assertEqual(self.snapshot(), before)

    def test_claim_uses_actor_company_and_preserves_author_status_number_and_finances(self):
        before = self.snapshot()
        original = self.available
        response = self.claim(
            empresa=self.company_b.pk, empresa_id=self.company_b.pk,
            usuario=self.operator_b.pk, status='F', assumido_por=self.operator_b.pk,
            ticket='FORGED001', descricao='Descrição forjada',
        )
        self.assertEqual(response.status_code, 302)
        saved = Ticket.objects.get(pk=original.pk)
        self.assertEqual(saved.empresa_id, self.company_a.pk)
        self.assertEqual(saved.assumido_por_id, self.operator_a.pk)
        self.assertIsNotNone(saved.assumido_em)
        for field in ('usuario_id', 'status', 'ticket', 'key', 'descricao', 'nfe_path'):
            self.assertEqual(getattr(saved, field), getattr(original, field))
        self.assertEqual(HistoricoTicket.objects.filter(ticket_historico=saved).count(), 1)
        after = self.snapshot()
        for model in before:
            if model not in (Ticket._meta.label_lower, HistoricoTicket._meta.label_lower):
                self.assertEqual(after[model], before[model], model)
        self.assertFalse(UsuarioEmpresa.objects.filter(usuario=self.subscriber).exists())

    def test_claim_is_idempotent_in_same_company_and_conflicts_for_another_company(self):
        self.claim_as_a()
        first_claim = self.snapshot()
        response = self.claim(user=self.manager_a)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.snapshot(), first_claim)
        response = self.claim(user=self.operator_b)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn(self.company_a.nome_fantasia, response.content.decode())
        self.assertNotIn(self.available.descricao, response.content.decode())
        self.assertEqual(self.snapshot(), first_claim)

    def test_superuser_must_explicitly_select_an_active_company_before_claiming(self):
        administrator = User.objects.create_superuser(
            username='admin_claim_validation', email='admin@example.invalid', password=None,
        )
        inactive = criar_empresa('Empresa inativa para administrador', '00.000.000/0000-04', ativa=False)
        self.client.force_login(administrator)
        before = self.snapshot()
        cases = (
            ({}, (400,)),
            ({'empresa': 'nao-e-um-id'}, (400, 404)),
            ({'empresa': str(inactive.pk)}, (400, 404)),
            ({'empresa': str(inactive.pk + self.company_b.pk + 1000)}, (400, 404)),
        )
        for payload, allowed_statuses in cases:
            with self.subTest(payload=payload):
                response = self.claim(**payload)
                self.assertIn(response.status_code, allowed_statuses)
                self.assertEqual(self.snapshot(), before)

    def test_superuser_can_claim_for_selected_company_preserving_independent_author(self):
        administrator = User.objects.create_superuser(
            username='admin_claim_company_b', email='admin-b@example.invalid', password=None,
        )
        before = self.snapshot()
        original = self.available
        response = self.claim(
            user=administrator, empresa=self.company_b.pk,
            usuario=self.operator_b.pk, status='F', assumido_por=self.operator_b.pk,
        )
        self.assertRedirects(response, self.url('exibir-ticket'), fetch_redirect_response=False)
        saved = Ticket.objects.get(pk=original.pk)
        self.assertEqual(saved.empresa_id, self.company_b.pk)
        self.assertEqual(saved.assumido_por_id, administrator.pk)
        self.assertIsNotNone(saved.assumido_em)
        for field in ('usuario_id', 'status', 'ticket', 'key', 'descricao', 'nfe_path'):
            self.assertEqual(getattr(saved, field), getattr(original, field))
        self.assertEqual(HistoricoTicket.objects.filter(ticket_historico=saved).count(), 1)
        after = self.snapshot()
        for model in before:
            if model not in (Ticket._meta.label_lower, HistoricoTicket._meta.label_lower):
                self.assertEqual(after[model], before[model], model)
        self.assertFalse(UsuarioEmpresa.objects.filter(usuario=self.subscriber).exists())

    def test_unassigned_ticket_without_author_is_not_available_or_claimable(self):
        orphan = Ticket.objects.create(
            ticket='ORPHAN001', usuario=None, empresa=None, status='L',
            descricao='Solicitação órfã fictícia',
        )
        before = self.snapshot()
        queue = self.client.get(reverse('tickets-disponiveis'))
        self.assertEqual(queue.status_code, 200)
        self.assertNotContains(queue, orphan.ticket)
        self.assertEqual(self.client.get(self.url('ticket-disponivel', orphan)).status_code, 404)
        response = self.client.post(self.url('assumir-ticket', orphan))
        self.assertIn(response.status_code, (404, 409))
        self.assertEqual(self.snapshot(), before)

    def test_claim_is_post_only_and_cannot_change_noneligible_ticket(self):
        before = self.snapshot()
        self.assertEqual(self.client.get(self.url('assumir-ticket')).status_code, 405)
        Ticket.objects.filter(pk=self.available.pk).update(status='E')
        progressed = self.snapshot()
        self.assertIn(self.claim().status_code, (404, 409))
        self.assertEqual(self.snapshot(), progressed)
        self.assertNotEqual(before[Ticket._meta.label_lower], progressed[Ticket._meta.label_lower])

    def test_missing_inactive_company_and_nonclaiming_roles_cannot_claim(self):
        missing = User.objects.create_user(username='operador_sem_empresa')
        assign_role(missing, 'operador')
        inactive_company = criar_empresa('Empresa inativa', '00.000.000/0000-03', ativa=False)
        inactive = User.objects.create_user(username='operador_empresa_inativa')
        assign_role(inactive, 'operador')
        vincular_usuario(inactive, inactive_company)
        actors = [missing, inactive, self.subscriber]
        for role in ('cliente', 'colaborador'):
            user = User.objects.create_user(username=f'{role}_sem_claim')
            assign_role(user, role)
            vincular_usuario(user, self.company_a)
            actors.append(user)
        before = self.snapshot()
        for user in actors:
            with self.subTest(user=user.username):
                response = self.claim(user=user)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.snapshot(), before)
        for user in (missing, inactive):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('tickets-disponiveis')).status_code, 403)

    def test_claimed_ticket_is_visible_to_company_team_and_independent_author(self):
        self.claim_as_a()
        for user in (self.operator_a, self.manager_a, self.subscriber):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse('index-tickets'))
                self.assertContains(response, self.available.ticket)
                self.assertEqual(self.client.get(self.url('exibir-ticket')).status_code, 200)
        self.client.force_login(self.subscriber)
        self.assertEqual(self.client.get(self.url('editar-ticket')).status_code, 200)
        self.assertEqual(self.claim().status_code, 403)
        self.assertFalse(UsuarioEmpresa.objects.filter(usuario=self.subscriber).exists())

    def test_other_company_cannot_find_claimed_ticket_in_queue_or_full_routes(self):
        self.claim_as_a()
        self.client.force_login(self.operator_b)
        for name in ('index-tickets', 'tickets-disponiveis', 'buscar_tickets'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.available.ticket)
        for name in ('ticket-disponivel', 'exibir-ticket', 'editar-ticket', 'gerar_pdf_ticket'):
            self.assertEqual(self.client.get(self.url(name)).status_code,
                             403 if name == 'gerar_pdf_ticket' else 404)

    @patch('tickets.views.HTML')
    def test_foreign_financial_and_mutation_endpoints_return_404_without_writes(self, renderer):
        self.claim_as_a()
        self.client.force_login(self.manager_b)
        key = self.available.key
        routes = (
            ('editar-ticket', {'key': key}), ('deletar-ticket', {'key': key}),
            ('update-historico', {'key': key}), ('add-pagamento', {'key': key}),
            ('editar-pagamento', {'pagamento_id': self.payment.pk, 'key': key}),
            ('deletar-pagamento', {'id': self.payment.pk, 'key': key}),
            ('editar-recebimento', {'recebimento_id': self.receipt.pk, 'key': key}),
            ('deletar-recebimento', {'recebimento_id': self.receipt.pk, 'key': key}),
            ('deletar-item', {'id': self.item.pk, 'key': key}),
            ('deletar-anexo', {'anexo_id': self.attachment.pk, 'key': key}),
            ('upload-nfe', {'key': key}), ('delete-nfe', {'key': key}),
            ('upload-comprovante', {'id': self.payment.pk, 'key': key}),
            ('delete-comprovante', {'id': self.payment.pk, 'key': key}),
            ('gerar_pdf_ticket', {'key': key}),
            ('gerar_pdf_orcamento', {'ticket_id': self.available.pk}),
        )
        before = self.snapshot()
        for name, arguments in routes:
            methods = ('get', 'post') if name.startswith('editar-') else (
                ('get',) if name in ('gerar_pdf_ticket', 'gerar_pdf_orcamento') else ('post',)
            )
            for method in methods:
                with self.subTest(route=name, method=method):
                    payload = {
                        'status': 'F', 'descricao': 'Alteração entre empresas',
                        'tipo': 'M', 'valor_pagamento': '999.99', 'data_pagamento': '2026-10-13',
                        'status_recebimento': 'True', 'valor_recebimento': '999.99',
                        'arquivo': SimpleUploadedFile('falso.pdf', b'fixture', 'application/pdf'),
                        'comprovante': SimpleUploadedFile('falso.pdf', b'fixture', 'application/pdf'),
                    }
                    response = getattr(self.client, method)(
                        reverse(name, kwargs=arguments), payload if method == 'post' else {},
                    )
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(self.snapshot(), before)
        renderer.assert_not_called()
        self.assertEqual(list(self.media_root.rglob('*')), [])

    def test_basic_company_roles_see_tracking_without_financial_modules(self):
        self.claim_as_a()
        for role in ('cliente', 'colaborador'):
            with self.subTest(role=role):
                user = User.objects.create_user(username=f'{role}_acompanhamento')
                assign_role(user, role)
                vincular_usuario(user, self.company_a)
                self.client.force_login(user)
                response = self.client.get(self.url('exibir-ticket'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.available.descricao)
                self.assertNotContains(response, self.budget.orcamento)
                self.assertNotContains(response, self.receipt.descricao_recebimento)
                self.assertNotContains(response, 'R$')
                self.assertRedirects(
                    self.client.get(reverse('dashboard')), reverse('index-tickets'),
                    fetch_redirect_response=False,
                )
                for url in (
                    reverse('relatorios'), self.url('gerar_pdf_ticket'),
                    self.url('editar-ticket'),
                ):
                    self.assertEqual(self.client.get(url).status_code, 403)


@skipUnless(connection.vendor == 'postgresql', 'Disputa real exige PostgreSQL.')
class AssumirTicketConcorrenteTests(TransactionTestCase):
    def test_two_companies_compete_for_one_ticket_and_only_one_claim_commits(self):
        companies = [
            criar_empresa(), criar_empresa('Empresa fictícia B', '00.000.000/0000-02'),
        ]
        actors = []
        for index, company in enumerate(companies):
            user = User.objects.create_user(username=f'concorrente_empresa_{index}')
            assign_role(user, 'operador')
            vincular_usuario(user, company)
            actors.append(user)
        author = User.objects.create_user(username='autor_concorrencia_independente')
        assign_role(author, 'assinante')
        ticket = Ticket.objects.create(ticket='CONCOR001', usuario=author, descricao='Disputa fictícia')
        codes_before = list(SequenciaTicket.objects.values())
        barrier = Barrier(2)
        outcomes = Queue()
        url = reverse('assumir-ticket', kwargs={'key': ticket.key})

        def claim(actor_id):
            database = connections['default']
            database.close()
            try:
                with database.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                client = Client()
                client.force_login(User.objects.get(pk=actor_id))
                barrier.wait(timeout=10)
                response = client.post(url)
                outcomes.put((actor_id, response.status_code, response.content.decode()))
            except Exception as error:
                outcomes.put((actor_id, 'error', f'{type(error).__name__}: {error}'))
            finally:
                database.close()

        threads = [Thread(target=claim, args=(actor.pk,), daemon=True) for actor in actors]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertFalse(any(thread.is_alive() for thread in threads), 'Thread não encerrou no prazo.')
        results = [outcomes.get_nowait() for _ in range(outcomes.qsize())]
        self.assertEqual(len(results), 2, results)
        self.assertTrue(all(isinstance(result[1], int) for result in results), results)
        self.assertEqual(sorted(result[1] for result in results), [302, 409], results)
        winner_id = next(actor_id for actor_id, status, _ in results if status == 302)
        loser_body = next(body for _, status, body in results if status == 409)
        winner_company_id = UsuarioEmpresa.objects.get(usuario_id=winner_id).empresa_id
        ticket.refresh_from_db()
        self.assertEqual(ticket.empresa_id, winner_company_id)
        self.assertEqual(ticket.assumido_por_id, winner_id)
        self.assertIsNotNone(ticket.assumido_em)
        self.assertEqual(ticket.usuario_id, author.pk)
        self.assertEqual(ticket.status, 'L')
        self.assertEqual(ticket.ticket, 'CONCOR001')
        self.assertEqual(HistoricoTicket.objects.filter(ticket_historico=ticket).count(), 1)
        self.assertEqual(list(SequenciaTicket.objects.values()), codes_before)
        self.assertNotIn(ticket.descricao, loser_body)
        winner_company_name = next(
            company.nome_fantasia for company in companies if company.pk == winner_company_id
        )
        self.assertNotIn(winner_company_name, loser_body)
