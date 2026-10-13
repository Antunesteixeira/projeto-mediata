from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid

from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rolepermissions.checkers import has_permission
from rolepermissions.roles import assign_role
from .models import UsuarioEmpresa
from .test_helpers import criar_empresa, vincular_usuario

from clientes.models import Cliente
from colaborador.models import Colaborador
from core.models import Empresa
from insumos.models import Insumos
from tickets.models import (
    Anexo, HistoricoTicket, ItemOrcamento, Orcamento, Pagamentos,
    Recebimentos, SequenciaTicket, Ticket,
)


class NavigationLinks(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.links = set()
        self.actions = set()
        self.anchors = []
        self.current_anchor = None
        self.feed(content)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'a' and attributes.get('href'):
            self.links.add(attributes['href'])
            self.current_anchor = (attributes['href'], [])
        if tag == 'form' and attributes.get('action'):
            self.actions.add(attributes['action'])

    def handle_data(self, content):
        if self.current_anchor is not None:
            self.current_anchor[1].append(content)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current_anchor is not None:
            href, content = self.current_anchor
            self.anchors.append((href, ' '.join(''.join(content).split())))
            self.current_anchor = None


class AssinanteAccessTests(TestCase):
    password = 'Fixture-Subscriber-Password-23!'

    @classmethod
    def setUpTestData(cls):
        cls.subscriber = User.objects.create_user(
            username='assinante_fixture', password=cls.password,
            first_name='Assinante', email='assinante@example.invalid',
        )
        assign_role(cls.subscriber, 'assinante')
        cls.subscriber_group = Group.objects.get(name='assinante')
        cls.operator = User.objects.create_user(username='operador_fixture')
        assign_role(cls.operator, 'operador')
        cls.manager = User.objects.create_user(username='gerente_fixture')
        assign_role(cls.manager, 'gerente')
        cls.administrator = User.objects.create_superuser(
            username='admin_fixture', email='admin@example.invalid',
            password=cls.password,
        )
        cls.customer = Cliente.objects.create(
            nome_razao_social='Cliente fictício', cpf_cnpj='00000000000',
        )
        cls.contractor = Colaborador.objects.create(nome_completo='Colaborador fictício')
        cls.company = Empresa.objects.create(
            nome_fantasia='Empresa fictícia', razao_social='Empresa fictícia LTDA',
            cnpj='00.000.000/0000-00', email='empresa@example.invalid',
            telefone='(00) 00000-0000', cep='00000-000', endereco='Rua fictícia',
            numero='1', bairro='Bairro fictício', cidade='Cidade fictícia', estado='PE',
        )
        cls.other_company = criar_empresa('Empresa fictícia B', '00.000.000/0000-02')
        vincular_usuario(cls.operator, cls.company)
        vincular_usuario(cls.manager, cls.company)
        cls.customer.empresa = cls.company
        cls.customer.save(update_fields=['empresa'])
        cls.contractor.empresa = cls.company
        cls.contractor.save(update_fields=['empresa'])
        cls.own_ticket = Ticket.objects.create(
            ticket='ASSN001', usuario=cls.subscriber, empresa=cls.company, status='E',
            descricao='Solicitação exclusiva do assinante',
            cliente=cls.customer, colaborador=cls.contractor,
            nfe_path='nfe/assinante-fixture.pdf',
        )
        cls.second_ticket = Ticket.objects.create(
            ticket='ASSN002', usuario=cls.subscriber,
            descricao='Segunda solicitação do assinante',
        )
        cls.foreign_ticket = Ticket.objects.create(
            ticket='FOREIGN01', usuario=cls.operator, empresa=cls.company,
            descricao='DESCRICAO-PRIVADA-OUTRO-USUARIO',
        )
        cls.history = HistoricoTicket.objects.create(
            ticket_historico=cls.own_ticket,
            descricao_historico='Solicitação recebida e execução iniciada',
        )
        HistoricoTicket.objects.create(
            ticket_historico=cls.foreign_ticket,
            descricao_historico='HISTORICO-PRIVADO-OUTRO-USUARIO',
        )
        cls.budget = Orcamento.objects.create(
            ticket_orcamento=cls.own_ticket, orcamento='ORCAMENTO-INTERNO',
            descricao='Escopo financeiro interno', valor_total=Decimal('87654.32'),
        )
        cls.supply = Insumos.objects.create(
            empresa=cls.company,
            codigo='INSFIX001', insumo='INSUMO-INTERNO', tipo='M',
            unidade='UN', valor_unit=Decimal('33.33'),
        )
        cls.budget_item = ItemOrcamento.objects.create(
            orcamento=cls.budget, item=cls.supply, quant=Decimal('3.00'),
        )
        cls.payment = Pagamentos.objects.create(
            ticket_pagamento=cls.own_ticket, tipo='M',
            valor_pagamento=Decimal('76543.21'), data_pagamento=date(2026, 10, 13),
            comprovante='comprovantes/pagamento-assinante-fixture.pdf',
        )
        cls.receipt = Recebimentos.objects.create(
            ticket_recebimento=cls.own_ticket,
            descricao_recebimento='RECEBIMENTO-INTERNO',
            valor_recebimento=Decimal('65432.10'),
        )
        cls.attachment = Anexo.objects.create(
            ticket_anexo=cls.own_ticket, arquivo='anexos/assinante-fixture.pdf',
            descricao_anexo='Anexo interno fictício',
        )

    def setUp(self):
        media = TemporaryDirectory(prefix='mediata-assinante-tests-')
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.media_root = Path(media.name)
        self.client.force_login(self.subscriber)

    def snapshot(self):
        models = (
            Ticket, SequenciaTicket, Orcamento, ItemOrcamento, HistoricoTicket, Pagamentos,
            Recebimentos, Anexo, Cliente, Colaborador, Insumos, Empresa,
            User, UsuarioEmpresa, Group, User.groups.through, User.user_permissions.through,
        )
        return {
            model._meta.label_lower: list(model.objects.order_by('pk').values())
            for model in models
        }

    def detail_url(self, ticket=None):
        return reverse('exibir-ticket', kwargs={'key': (ticket or self.own_ticket).key})

    def navigation(self, response):
        return NavigationLinks(response.content.decode())

    def editable_ticket(self, number='EDITL001'):
        return Ticket.objects.create(
            ticket=number, usuario=self.subscriber, empresa=self.company, status='L',
            descricao='Solicitação editável em levantamento',
            cliente=self.customer, colaborador=self.contractor,
            emergencial=True, data_finalizar=date(2026, 10, 20),
            valor_material=Decimal('25.00'), valor_mao_obra=Decimal('50.00'),
            valor_custo=Decimal('75.00'), valor_faturamento=Decimal('100.00'),
            valor_equipamento=Decimal('10.00'), nfe_path='nfe/edicao-fixture.pdf',
        )

    def assert_only_permitted_edit_and_audit(self, before, record, **changes):
        after = self.snapshot()
        expected = {model: [dict(row) for row in rows] for model, rows in before.items()}
        for row in expected[Ticket._meta.label_lower]:
            if row['id'] == record.pk:
                row.update(changes)
        history_label = HistoricoTicket._meta.label_lower
        previous_ids = {row['id'] for row in before[history_label]}
        new_history = [row for row in after[history_label] if row['id'] not in previous_ids]
        self.assertEqual(len(new_history), 1)
        self.assertEqual(new_history[0]['ticket_historico_id'], record.pk)
        self.assertEqual(
            new_history[0]['descricao_historico'],
            'Dados da solicitação atualizados pelo assinante.',
        )
        expected[history_label].extend(new_history)
        expected[history_label].sort(key=lambda row: row['id'])
        self.assertEqual(after, expected)

    def mutation_routes(self):
        key = self.own_ticket.key
        return (
            ('editar-ticket', {'key': key}),
            ('deletar-ticket', {'key': key}),
            ('update-historico', {'key': key}),
            ('deletar-item', {'id': self.budget_item.pk, 'key': key}),
            ('add-pagamento', {'key': key}),
            ('editar-pagamento', {'pagamento_id': self.payment.pk, 'key': key}),
            ('deletar-pagamento', {'id': self.payment.pk, 'key': key}),
            ('editar-recebimento', {'recebimento_id': self.receipt.pk, 'key': key}),
            ('deletar-recebimento', {'recebimento_id': self.receipt.pk, 'key': key}),
            ('deletar-anexo', {'anexo_id': self.attachment.pk, 'key': key}),
            ('upload-nfe', {'key': key}),
            ('upload-comprovante', {'id': self.payment.pk, 'key': key}),
            ('delete-nfe', {'key': key}),
            ('delete-comprovante', {'id': self.payment.pk, 'key': key}),
            ('add-cliente-ticket', {'id_ticket': self.own_ticket.pk}),
            ('cadastrar-cliente-ticket', {
                'id_cliente': self.customer.pk, 'id_ticket': self.own_ticket.pk,
            }),
            ('add-colaborador-ticket', {'id_ticket': self.own_ticket.pk}),
            ('cadastrar-colaborador-ticket', {
                'id_ticket': self.own_ticket.pk, 'id_colaborador': self.contractor.pk,
            }),
            ('gerar_pdf_ticket', {'key': key}),
            ('gerar_pdf_orcamento', {'ticket_id': self.own_ticket.pk}),
        )

    def blocked_module_routes(self):
        return (
            ('relatorios', {}), ('listar-clientes', {}),
            ('cadastrar-cliente', {}), ('editar-cliente', {'cliente_id': self.customer.pk}),
            ('deletar-cliente', {'cliente_id': self.customer.pk}),
            ('perfil_cliente', {'id': self.customer.pk}),
            ('lista_colaboradores', {}), ('cadastrar_colaborador', {}),
            ('editar-colaborador', {'colaborador_id': self.contractor.pk}),
            ('deletar-colaborador', {'colaborador_id': self.contractor.pk}),
            ('perfil_colaborador', {'id': self.contractor.pk}),
            ('criar_usuario_colaborador', {'colaborador_id': self.contractor.pk}),
            ('index-insumos', {}), ('editar-insumos', {'id': self.supply.pk}),
            ('deletar-insumos', {'id': self.supply.pk}), ('buscar-itens', {}),
            ('index-usuarios', {}), ('registrar-usuarios', {}),
            ('editar-usuario', {'user_id': self.subscriber.pk}),
            ('editar-usuarios', {'id': self.subscriber.pk}),
            ('empresa_lista', {}), ('empresa_cadastrar', {}),
            ('empresa_editar', {'pk': self.company.pk}),
            ('empresa_perfil', {'pk': self.company.pk}), ('empresa_success', {}),
            ('admin:index', {}), ('admin:login', {}), ('admin:auth_user_changelist', {}),
        )

    def assert_routes_forbidden_without_changes(self, routes):
        before = self.snapshot()
        for name, arguments in routes:
            url = reverse(name, kwargs=arguments)
            for method in ('get', 'post'):
                with self.subTest(route=name, method=method):
                    payload = {
                        'status': 'F', 'descricao': 'Alteração não autorizada',
                        'tipo': 'M', 'valor_pagamento': '999.99',
                        'data_pagamento': '2026-10-13', 'status_pagamento': 'on',
                        'valor_recebimento': '999.99', 'status_recebimento': 'True',
                        'username': 'usuario_nao_autorizado', 'groups': self.subscriber_group.pk,
                        'arquivo': SimpleUploadedFile('ficticio.pdf', b'fixture', 'application/pdf'),
                        'comprovante': SimpleUploadedFile('ficticio.pdf', b'fixture', 'application/pdf'),
                    }
                    response = getattr(self.client, method)(url, payload if method == 'post' else {})
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.media_root.rglob('*')), [])

    def test_home_and_dashboard_redirect_to_own_ticket_list(self):
        for name in ('index', 'dashboard'):
            for method in ('get', 'head'):
                with self.subTest(route=name, method=method):
                    response = getattr(self.client, method)(reverse(name))
                    self.assertRedirects(
                        response, reverse('index-tickets'), fetch_redirect_response=False,
                    )

    def test_ticket_list_contains_only_owned_tickets_and_no_management_links(self):
        response = self.client.get(reverse('index-tickets'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_assinante'])
        self.assertContains(response, self.own_ticket.ticket)
        self.assertContains(response, self.second_ticket.ticket)
        self.assertNotContains(response, self.foreign_ticket.ticket)
        self.assertNotContains(response, self.foreign_ticket.descricao)
        navigation = self.navigation(response)
        self.assertIn(reverse('cadastro-ticket'), navigation.links)
        self.assertIn(self.detail_url(), navigation.links)
        for name, arguments in self.mutation_routes() + self.blocked_module_routes():
            with self.subTest(route=name):
                self.assertNotIn(reverse(name, kwargs=arguments), navigation.links | navigation.actions)

    def test_search_with_and_without_a_term_never_exposes_foreign_tickets(self):
        for parameters, expected in (
            ({}, (self.own_ticket, self.second_ticket)),
            ({'q': 'ASSN'}, (self.own_ticket, self.second_ticket)),
            ({'q': self.own_ticket.ticket}, (self.own_ticket,)),
            ({'term': self.second_ticket.ticket}, (self.second_ticket,)),
            ({'q': self.foreign_ticket.ticket}, ()),
        ):
            with self.subTest(parameters=parameters):
                response = self.client.get(reverse('buscar_tickets'), parameters)
                self.assertEqual(response.status_code, 200)
                for ticket in expected:
                    self.assertContains(response, ticket.ticket)
                self.assertNotContains(response, self.foreign_ticket.ticket)
                self.assertNotContains(response, self.foreign_ticket.descricao)
                expected_ids = {ticket.pk for ticket in expected}
                self.assertEqual({ticket.pk for ticket in response.context['tickets']}, expected_ids)

    def test_own_detail_shows_status_and_history_without_financial_data_or_writes(self):
        before = self.snapshot()
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tickets/acompanhamento-ticket.html')
        self.assertContains(response, self.own_ticket.descricao)
        self.assertContains(response, self.own_ticket.get_status_display())
        self.assertContains(response, self.history.descricao_historico)
        for private_text in (
            'HISTORICO-PRIVADO-OUTRO-USUARIO', self.budget.orcamento,
            self.supply.insumo, self.receipt.descricao_recebimento,
            self.payment.comprovante, self.own_ticket.nfe_path, 'R$',
        ):
            with self.subTest(private_text=private_text):
                self.assertNotContains(response, private_text)
        navigation = self.navigation(response)
        for name, arguments in self.mutation_routes():
            self.assertNotIn(reverse(name, kwargs=arguments), navigation.links | navigation.actions)
        self.assertEqual(self.client.head(self.detail_url()).status_code, 200)
        self.assertEqual(self.snapshot(), before)

    def test_foreign_and_unknown_ticket_details_return_404(self):
        for key in (self.foreign_ticket.key, uuid.uuid4()):
            with self.subTest(key=key):
                response = self.client.get(reverse('exibir-ticket', kwargs={'key': key}))
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(self.foreign_ticket.descricao, response.content.decode())

    def test_creation_form_exposes_optional_number_and_description(self):
        response = self.client.get(reverse('cadastro-ticket'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_assinante'])
        self.assertEqual(set(response.context['form'].fields), {'ticket', 'descricao'})
        self.assertFalse(response.context['form'].fields['ticket'].required)

    def test_creation_ignores_forged_identity_status_and_financial_fields(self):
        before_ids = set(Ticket.objects.values_list('pk', flat=True))
        payload = {
            'descricao': 'Solicitação criada com campos extras forjados',
            'ticket': 'MANASS001', 'id': self.foreign_ticket.pk,
            'key': str(self.foreign_ticket.key), 'usuario': self.operator.pk,
            'usuario_id': self.operator.pk, 'status': 'F',
            'cliente': self.customer.pk, 'colaborador': self.contractor.pk,
            'emergencial': 'on', 'finalizado': 'on', 'data_finalizar': '2030-01-01',
            'nfe_path': 'nfe/forjada.pdf',
            'empresa': self.other_company.pk, 'empresa_id': self.other_company.pk,
            'assumido_por': self.operator.pk,
            **{field: '99999.99' for field in (
                'valor_material', 'valor_mao_obra', 'valor_custo',
                'valor_faturamento', 'valor_equipamento',
            )},
        }
        response = self.client.post(reverse('cadastro-ticket'), payload)
        self.assertEqual(response.status_code, 302)
        created = Ticket.objects.exclude(pk__in=before_ids).get()
        self.assertEqual(created.descricao, payload['descricao'])
        self.assertEqual(created.usuario_id, self.subscriber.pk)
        self.assertEqual(created.status, 'L')
        self.assertIsNone(created.empresa_id)
        self.assertIsNone(created.assumido_por_id)
        self.assertFalse(UsuarioEmpresa.objects.filter(usuario=self.subscriber).exists())
        self.assertEqual(created.ticket, payload['ticket'])
        self.assertNotEqual(created.key, self.foreign_ticket.key)
        self.assertIsNone(created.cliente_id)
        self.assertIsNone(created.colaborador_id)
        self.assertFalse(created.emergencial)
        self.assertFalse(created.finalizado)
        self.assertIsNone(created.data_finalizar)
        self.assertFalse(created.nfe_path)
        for field, value in (
            ('valor_material', '0'), ('valor_mao_obra', '0'),
            ('valor_custo', '0'), ('valor_faturamento', '1'), ('valor_equipamento', '0'),
        ):
            with self.subTest(field=field):
                self.assertEqual(getattr(created, field), Decimal(value))
        response = self.client.post(reverse('cadastro-ticket'), {'descricao': 'Segunda criação válida'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Ticket.objects.count(), len(before_ids) + 2)
        self.assertEqual(Ticket.objects.values('ticket').distinct().count(), Ticket.objects.count())

    def test_blank_description_does_not_create_a_ticket(self):
        before = self.snapshot()
        response = self.client.post(reverse('cadastro-ticket'), {'descricao': '   '})
        self.assertEqual(response.status_code, 200)
        self.assertIn('descricao', response.context['form'].errors)
        self.assertEqual(self.snapshot(), before)

    def test_own_levantamento_ticket_has_edit_links_and_restricted_read_only_get(self):
        ticket = self.editable_ticket()
        url = reverse('editar-ticket', kwargs={'key': ticket.key})
        before = self.snapshot()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_assinante'])
        form = response.context['form']
        self.assertEqual(set(form.fields), {'ticket', 'descricao'})
        self.assertFalse(form.fields['ticket'].required)
        self.assertEqual(form['ticket'].value(), ticket.ticket)
        self.assertEqual(form['descricao'].value(), ticket.descricao)
        self.assertNotContains(response, 'name="status"')
        cancel_links = [href for href, label in self.navigation(response).anchors if label == 'Cancelar']
        self.assertEqual(set(cancel_links), {self.detail_url(ticket)})
        self.assertEqual(self.client.head(url).status_code, 200)
        for method in ('PUT', 'PATCH', 'DELETE'):
            with self.subTest(method=method):
                self.assertEqual(self.client.generic(method, url).status_code, 403)
        for page in (reverse('index-tickets'), self.detail_url(ticket)):
            with self.subTest(page=page):
                response = self.client.get(page)
                self.assertIn(url, self.navigation(response).links)
                self.assertNotIn(
                    reverse('editar-ticket', kwargs={'key': self.own_ticket.key}),
                    self.navigation(response).links,
                )
        self.assertEqual(self.snapshot(), before)

    def test_edit_ignores_protected_fields_even_for_staff_with_mixed_groups(self):
        ticket = self.editable_ticket()
        other_customer = Cliente.objects.create(
            empresa=self.other_company, nome_razao_social='Outro cliente fictício', cpf_cnpj='00000000001',
        )
        other_contractor = Colaborador.objects.create(empresa=self.other_company, nome_completo='Outro colaborador fictício')
        self.subscriber.groups.add(Group.objects.get(name='gerente'))
        self.subscriber.is_staff = True
        self.subscriber.save(update_fields=['is_staff'])
        self.client.force_login(self.subscriber)
        before = self.snapshot()
        response = self.client.post(reverse('editar-ticket', kwargs={'key': ticket.key}), {
            'ticket': 'SUBEDIT01', 'descricao': 'Descrição autorizada do assinante',
            'status': 'F', 'usuario': self.operator.pk, 'usuario_id': self.operator.pk,
            'id': self.foreign_ticket.pk, 'key': str(self.foreign_ticket.key),
            'cliente': other_customer.pk, 'cliente_id': other_customer.pk,
            'colaborador': other_contractor.pk, 'colaborador_id': other_contractor.pk,
            'emergencial': '', 'finalizado': 'on', 'data_finalizar': '2030-01-01',
            'nfe_path': 'nfe/forjada.pdf', 'descricao_historico': 'Histórico forjado',
            'empresa': self.other_company.pk, 'empresa_id': self.other_company.pk,
            'assumido_por': self.operator.pk,
            'valor_recebimento': '777.77', 'valor_pagamento': '777.77',
            **{field: '777.77' for field in (
                'valor_material', 'valor_mao_obra', 'valor_custo',
                'valor_faturamento', 'valor_equipamento',
            )},
        })
        self.assertRedirects(response, self.detail_url(ticket), fetch_redirect_response=False)
        self.assert_only_permitted_edit_and_audit(
            before, ticket, ticket='SUBEDIT01', descricao='Descrição autorizada do assinante',
        )

    def test_blank_edit_number_preserves_code_identity_and_counter(self):
        ticket = self.editable_ticket(number='2610123')
        before = self.snapshot()
        response = self.client.post(reverse('editar-ticket', kwargs={'key': ticket.key}), {
            'ticket': '   ', 'descricao': 'Descrição corrigida sem mudar o número',
        })
        self.assertRedirects(response, self.detail_url(ticket), fetch_redirect_response=False)
        self.assert_only_permitted_edit_and_audit(
            before, ticket, descricao='Descrição corrigida sem mudar o número',
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.ticket, '2610123')
        self.assertEqual(ticket.status, 'L')

    def test_edit_without_actual_changes_creates_no_audit_or_number(self):
        ticket = self.editable_ticket()
        before = self.snapshot()
        response = self.client.post(reverse('editar-ticket', kwargs={'key': ticket.key}), {
            'ticket': '', 'descricao': ticket.descricao,
        })
        self.assertRedirects(response, self.detail_url(ticket), fetch_redirect_response=False)
        self.assertEqual(self.snapshot(), before)

    def test_all_other_statuses_block_edit_and_hide_edit_links(self):
        ticket = self.editable_ticket()
        url = reverse('editar-ticket', kwargs={'key': ticket.key})
        for status, _ in Ticket.STATUS_CHOICES:
            if status == 'L':
                continue
            with self.subTest(status=status):
                Ticket.objects.filter(pk=ticket.pk).update(status=status)
                before = self.snapshot()
                for method in ('get', 'head', 'post'):
                    with self.subTest(method=method):
                        payload = {'ticket': ticket.ticket, 'descricao': 'Edição bloqueada', 'status': 'L'}
                        response = getattr(self.client, method)(url, payload if method == 'post' else {})
                        self.assertEqual(response.status_code, 403)
                for page in (reverse('index-tickets'), self.detail_url(ticket)):
                    self.assertNotIn(url, self.navigation(self.client.get(page)).links)
                self.assertEqual(self.snapshot(), before)

    def test_foreign_or_unknown_edit_urls_return_404_even_in_levantamento(self):
        before = self.snapshot()
        for key in (self.foreign_ticket.key, uuid.uuid4()):
            for method in ('get', 'head', 'post'):
                with self.subTest(key=key, method=method):
                    url = reverse('editar-ticket', kwargs={'key': key})
                    payload = {
                        'ticket': 'FORGED01', 'descricao': 'Edição de outro usuário',
                        'usuario': self.subscriber.pk, 'status': 'L',
                    }
                    response = getattr(self.client, method)(url, payload if method == 'post' else {})
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn(self.foreign_ticket.descricao, response.content.decode())
        self.assertEqual(self.snapshot(), before)

    def test_manager_status_change_after_form_open_blocks_stale_post(self):
        ticket = self.editable_ticket()
        url = reverse('editar-ticket', kwargs={'key': ticket.key})
        self.assertEqual(self.client.get(url).status_code, 200)
        manager_client = Client()
        manager_client.force_login(self.manager)
        response = manager_client.post(reverse('update-historico', kwargs={'key': ticket.key}), {'status': 'E'})
        self.assertRedirects(response, self.detail_url(ticket), fetch_redirect_response=False)
        before = self.snapshot()
        response = self.client.post(url, {
            'ticket': 'STALE001', 'descricao': 'Descrição de formulário desatualizado',
            'status': 'L',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.snapshot(), before)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'E')

    def test_edit_duplicate_manual_code_reappears_as_error_without_saving(self):
        ticket = self.editable_ticket()
        before = self.snapshot()
        response = self.client.post(reverse('editar-ticket', kwargs={'key': ticket.key}), {
            'ticket': self.foreign_ticket.ticket, 'descricao': 'Alteração que não deve ser salva',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('ticket', response.context['form'].errors)
        self.assertContains(response, str(response.context['form'].errors['ticket'][0]))
        cancel_links = [href for href, label in self.navigation(response).anchors if label == 'Cancelar']
        self.assertEqual(set(cancel_links), {self.detail_url(ticket)})
        self.assertEqual(self.snapshot(), before)

    def test_levantamento_does_not_enable_other_mutations_or_detail_post(self):
        Ticket.objects.filter(pk=self.own_ticket.pk).update(status='L')
        self.assert_routes_forbidden_without_changes(tuple(
            route for route in self.mutation_routes() if route[0] != 'editar-ticket'
        ))
        before = self.snapshot()
        response = self.client.post(self.detail_url(), {
            'form_type': 'orcamento', 'orcamento-orcamento': 'Orçamento indevido',
            'orcamento-descricao': 'Não autorizado',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.snapshot(), before)

    def test_other_roles_keep_full_edit_form_and_can_edit_outside_levantamento(self):
        ticket = Ticket.objects.create(
            ticket='ROLEEDIT01', usuario=self.operator, empresa=self.company, status='E',
            descricao='Ticket para fluxo normal de edição',
        )
        url = reverse('editar-ticket', kwargs={'key': ticket.key})
        for user in (self.operator, self.manager, self.administrator):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context['is_assinante'])
                self.assertIn('status', response.context['form'].fields)
                self.assertIn('data_finalizar', response.context['form'].fields)
                response = self.client.post(url, {
                    'ticket': ticket.ticket, 'descricao': f'Edição normal por {user.username}',
                    'status': 'V', 'data_finalizar': '2026-10-31',
                })
                self.assertRedirects(response, reverse('index-tickets'), fetch_redirect_response=False)
                ticket.refresh_from_db()
                self.assertEqual(ticket.status, 'V')
                self.assertEqual(ticket.descricao, f'Edição normal por {user.username}')

    def test_direct_ticket_mutation_and_pdf_urls_are_forbidden(self):
        self.assert_routes_forbidden_without_changes(self.mutation_routes())

    def test_other_modules_and_admin_urls_are_forbidden_even_when_named_login(self):
        self.assert_routes_forbidden_without_changes(self.blocked_module_routes())

    def test_post_to_own_detail_cannot_create_budgets_payments_receipts_or_uploads(self):
        before = self.snapshot()
        for form_type in ('orcamento', 'itemorcamento', 'form-pagamento', 'recebimentos_form', 'anexo'):
            with self.subTest(form_type=form_type):
                response = self.client.post(self.detail_url(), {
                    'form_type': form_type, 'status': 'F',
                    'orcamento-orcamento': 'Orçamento indevido',
                    'orcamento-descricao': 'Não autorizado',
                    'item': self.supply.pk, 'quant': '2', 'tipo': 'M',
                    'valor_pagamento': '100.00', 'data_pagamento': '2026-10-13',
                    'valor_recebimento': '100.00', 'status_recebimento': 'True',
                    'arquivo': SimpleUploadedFile('anexo.pdf', b'fixture', 'application/pdf'),
                })
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.media_root.rglob('*')), [])

    def test_read_only_routes_and_unsupported_http_methods_reject_writes(self):
        before = self.snapshot()
        for url in (
            reverse('index'), reverse('dashboard'), reverse('index-tickets'),
            reverse('buscar_tickets'), reverse('perfil-usuario', kwargs={'id': self.subscriber.pk}),
        ):
            with self.subTest(url=url, method='POST'):
                self.assertEqual(self.client.post(url, {'status': 'F'}).status_code, 403)
        for url in (reverse('cadastro-ticket'), self.detail_url()):
            for method in ('PUT', 'PATCH', 'DELETE'):
                with self.subTest(url=url, method=method):
                    self.assertEqual(self.client.generic(method, url).status_code, 403)
        self.assertEqual(self.snapshot(), before)

    def test_only_own_profile_is_accessible_and_has_no_edit_link(self):
        response = self.client.get(reverse('perfil-usuario', kwargs={'id': self.subscriber.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.subscriber.username)
        self.assertTrue(response.context['is_assinante'])
        navigation = self.navigation(response)
        self.assertNotIn(
            reverse('editar-usuario', kwargs={'user_id': self.subscriber.pk}), navigation.links,
        )
        for user_id in (self.operator.pk, self.administrator.pk):
            with self.subTest(user_id=user_id):
                response = self.client.get(reverse('perfil-usuario', kwargs={'id': user_id}))
                self.assertIn(response.status_code, (403, 404))

    def test_staff_and_mixed_manager_membership_do_not_bypass_restrictions(self):
        manager_group = Group.objects.get(name='gerente')
        for staff, mixed_groups in ((True, False), (False, True), (True, True)):
            with self.subTest(staff=staff, mixed_groups=mixed_groups):
                self.subscriber.is_staff = staff
                self.subscriber.save(update_fields=['is_staff'])
                groups = [self.subscriber_group, manager_group] if mixed_groups else [self.subscriber_group]
                self.subscriber.groups.set(groups)
                self.client.force_login(self.subscriber)
                response = self.client.get(reverse('index-tickets'))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['is_assinante'])
                self.assertNotContains(response, self.foreign_ticket.ticket)
                before = self.snapshot()
                for url in (
                    reverse('admin:index'), reverse('index-usuarios'), reverse('relatorios'),
                    reverse('editar-ticket', kwargs={'key': self.own_ticket.key}),
                ):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, {'status': 'F'}).status_code, 403)
                self.assertEqual(self.client.get(self.detail_url(self.foreign_ticket)).status_code, 404)
                self.assertEqual(self.snapshot(), before)

    def test_superuser_with_subscriber_group_keeps_administrative_access(self):
        self.administrator.groups.add(self.subscriber_group)
        self.client.force_login(self.administrator)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_assinante'])
        self.assertEqual(self.client.get(reverse('index-usuarios')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)

    def test_existing_operator_and_manager_remain_outside_subscriber_mode(self):
        for user in (self.operator, self.manager):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse('index-tickets'))
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context['is_assinante'])
                self.assertEqual(
                    self.client.get(reverse('editar-ticket', kwargs={'key': self.foreign_ticket.key})).status_code,
                    200,
                )

    def test_superuser_can_register_an_independent_subscriber(self):
        self.client.force_login(self.administrator)
        response = self.client.get(reverse('registrar-usuarios'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].fields['group'].queryset.filter(
            pk=self.subscriber_group.pk,
        ).exists())
        response = self.client.post(reverse('registrar-usuarios'), {
            'username': 'novo_assinante_fixture',
            'email': 'novo-assinante@example.invalid',
            'password1': self.password, 'password2': self.password,
            'group': self.subscriber_group.pk,
        })
        self.assertEqual(
            response.status_code, 302,
            response.context['form'].errors if response.status_code == 200 else None,
        )
        created = User.objects.get(username='novo_assinante_fixture')
        self.assertTrue(created.groups.filter(pk=self.subscriber_group.pk).exists())
        self.assertFalse(UsuarioEmpresa.objects.filter(usuario=created).exists())
        self.assertTrue(has_permission(created, 'criar_ticket'))
        self.assertTrue(has_permission(created, 'ver_ticket'))
        self.client.force_login(created)
        self.assertEqual(self.client.get(reverse('index-usuarios')).status_code, 403)

    def test_superuser_can_assign_independent_subscriber_group(self):
        self.client.force_login(self.administrator)
        response = self.client.get(reverse('editar-usuario', kwargs={'user_id': self.operator.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].fields['groups'].queryset.filter(
            pk=self.subscriber_group.pk,
        ).exists())
        response = self.client.post(reverse('editar-usuario', kwargs={'user_id': self.operator.pk}), {
            'username': self.operator.username, 'first_name': 'Novo assinante',
            'last_name': '', 'email': 'novo@example.invalid',
            'groups': self.subscriber_group.pk, 'is_active': 'on',
            'empresa': '',
        })
        self.assertRedirects(response, reverse('index-usuarios'), fetch_redirect_response=False)
        self.operator.refresh_from_db()
        self.assertEqual(list(self.operator.groups.values_list('pk', flat=True)), [self.subscriber_group.pk])
        self.assertFalse(UsuarioEmpresa.objects.filter(usuario=self.operator).exists())
        self.assertTrue(has_permission(self.operator, 'criar_ticket'))
        self.assertTrue(has_permission(self.operator, 'ver_ticket'))
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('relatorios')).status_code, 403)

    def test_password_change_is_allowed_and_changes_only_the_subscribers_password(self):
        original_operator_password = self.operator.password
        group_ids = set(self.subscriber.groups.values_list('pk', flat=True))
        response = self.client.get(reverse('password_change'))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('password_change'), {
            'old_password': self.password,
            'new_password1': 'Changed-Fixture-Subscriber-73!',
            'new_password2': 'Changed-Fixture-Subscriber-73!',
            'user_id': self.operator.pk,
        })
        self.assertRedirects(response, reverse('password_change_done'))
        self.subscriber.refresh_from_db()
        self.operator.refresh_from_db()
        self.assertTrue(self.subscriber.check_password('Changed-Fixture-Subscriber-73!'))
        self.assertEqual(self.operator.password, original_operator_password)
        self.assertEqual(set(self.subscriber.groups.values_list('pk', flat=True)), group_ids)
        self.assertEqual(self.client.get(reverse('index-tickets')).status_code, 200)

    def test_logout_is_allowed_for_both_routes_and_ends_the_session(self):
        for url in (reverse('logout'), '/accounts/logout/'):
            with self.subTest(url=url):
                self.client.force_login(self.subscriber)
                response = self.client.post(url)
                self.assertRedirects(response, reverse('login'), fetch_redirect_response=False)
                self.assertNotIn(SESSION_KEY, self.client.session)
                response = self.client.get(reverse('index-tickets'))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response.url)
