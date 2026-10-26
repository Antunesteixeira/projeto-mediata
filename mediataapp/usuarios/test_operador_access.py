"""O operador atende somente os tickets que cadastrou na própria empresa."""

from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.state import ProjectState
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rolepermissions.roles import assign_role

from clientes.models import Cliente
from colaborador.models import Colaborador
from core.tenancy import pode_acessar_financeiro, pode_gerenciar_empresa, pode_operar_tickets
from financeiro.models import LancamentoManual
from financeiro.services import fontes_financeiras
from insumos.models import Insumos
from tickets.models import (
    Anexo, HistoricoTicket, ItemOrcamento, Orcamento, Pagamentos,
    Recebimentos, SequenciaTicket, Ticket,
)
from .models import UsuarioEmpresa
from .test_helpers import criar_empresa, vincular_usuario


@override_settings(TIME_ZONE='America/Sao_Paulo')
class OperadorAccessTests(TestCase):
    financial_fields = (
        'valor_material', 'valor_mao_obra', 'valor_custo',
        'valor_faturamento', 'valor_equipamento',
    )

    @classmethod
    def setUpTestData(cls):
        cls.empresa = criar_empresa('Operação de teste A', '00.000.000/0000-91')
        cls.outra_empresa = criar_empresa('Operação de teste B', '00.000.000/0000-92')
        cls.operador = cls.usuario('operacao_restrita', 'operador', cls.empresa)
        cls.colega = cls.usuario('operacao_colega', 'operador', cls.empresa)
        cls.gerente = cls.usuario('gestao_operacao', 'gerente', cls.empresa)
        cls.estrangeiro = cls.usuario('operacao_estrangeira', 'operador', cls.outra_empresa)
        cls.assinante = cls.usuario('cliente_independente_operacao', 'assinante')
        cls.superusuario = User.objects.create_superuser(
            username='administracao_operacao', email='admin@example.invalid', password=None,
        )
        cls.cliente = Cliente.objects.create(
            empresa=cls.empresa, nome_razao_social='Cliente operacional A', cpf_cnpj='00000000091',
        )
        cls.cliente_estrangeiro = Cliente.objects.create(
            empresa=cls.outra_empresa, nome_razao_social='Cliente privado B', cpf_cnpj='00000000092',
        )
        cls.colaborador = Colaborador.objects.create(
            empresa=cls.empresa, nome_completo='Prestador operacional A',
            banco='BANCO-OP91', conta='CONTAOP91', chave_pix='PIX-OP91',
        )
        cls.colaborador_estrangeiro = Colaborador.objects.create(
            empresa=cls.outra_empresa, nome_completo='Prestador privado B',
        )
        cls.ticket = Ticket.objects.create(
            ticket='OPSEG001', empresa=cls.empresa, usuario=cls.operador,
            assumido_por=cls.operador, status='L', descricao='Atendimento operacional A',
            cliente=cls.cliente, colaborador=cls.colaborador,
            nfe_path='nfe/nota-operacao-restrita.pdf',
            valor_material=Decimal('91234.56'), valor_mao_obra=Decimal('81234.57'),
            valor_custo=Decimal('71234.58'), valor_faturamento=Decimal('61234.59'),
            valor_equipamento=Decimal('51234.60'),
        )
        cls.ticket_colega = Ticket.objects.create(
            ticket='OPSEG002', empresa=cls.empresa, usuario=cls.colega,
            assumido_por=cls.operador, descricao='Atendimento criado pelo colega e atribuído ao operador',
        )
        cls.ticket_estrangeiro = Ticket.objects.create(
            ticket='OPSEG003', empresa=cls.outra_empresa, usuario=cls.operador,
            assumido_por=cls.operador, descricao='Atendimento de autoria do operador em outra empresa',
        )
        cls.disponivel = Ticket.objects.create(
            ticket='OPSEG004', usuario=cls.assinante, descricao='Solicitação disponível independente',
        )
        cls.ticket_gerente = Ticket.objects.create(
            ticket='OPSEG005', empresa=cls.empresa, usuario=cls.gerente,
            assumido_por=cls.operador, descricao='Atendimento criado pelo gerente e atribuído ao operador',
        )
        cls.ticket_assinante = Ticket.objects.create(
            ticket='OPSEG006', empresa=cls.empresa, usuario=cls.assinante,
            assumido_por=cls.operador, descricao='Atendimento criado pelo cliente e atribuído ao operador',
        )
        cls.ticket_proprio = Ticket.objects.create(
            ticket='OPSEG007', empresa=cls.empresa, usuario=cls.operador,
            assumido_por=cls.gerente, descricao='Atendimento do operador atribuído ao gerente',
        )
        cliente_restrito = Cliente.objects.create(
            empresa=cls.empresa, nome_razao_social='Cliente exclusivo dos tickets de terceiros',
            cpf_cnpj='00000000093',
        )
        colaborador_restrito = Colaborador.objects.create(
            empresa=cls.empresa, nome_completo='Prestador exclusivo dos tickets de terceiros',
        )
        Ticket.objects.filter(pk__in=(cls.ticket_colega.pk, cls.ticket_gerente.pk,
                                     cls.ticket_assinante.pk)).update(
            cliente=cliente_restrito, colaborador=colaborador_restrito,
        )
        cls.insumo = Insumos.objects.create(
            empresa=cls.empresa, codigo='OPINS001', insumo='INSUMO-FINANCEIRO-RESTRITO',
            tipo='M', unidade='UN', valor_unit=Decimal('41234.61'),
        )
        cls.orcamento = Orcamento.objects.create(
            ticket_orcamento=cls.ticket, orcamento='ORCAMENTO-FINANCEIRO-RESTRITO',
            descricao='DESCRICAO-FINANCEIRA-RESTRITA', valor_total=Decimal('31234.62'),
        )
        cls.item = ItemOrcamento.objects.create(
            orcamento=cls.orcamento, item=cls.insumo, quant=Decimal('1'),
        )
        cls.pagamento = Pagamentos.objects.create(
            ticket_pagamento=cls.ticket, tipo='M', valor_pagamento=Decimal('21234.63'),
            comprovante='comprovantes/pagamento-operacao-restrita.pdf',
        )
        cls.recebimento = Recebimentos.objects.create(
            ticket_recebimento=cls.ticket, valor_recebimento=Decimal('11234.64'),
            descricao_recebimento='RECEBIMENTO-FINANCEIRO-RESTRITO',
            comprovante_recebimento='comprovantes/recebimento-operacao-restrita.pdf',
        )
        cls.anexo = Anexo.objects.create(
            ticket_anexo=cls.ticket, arquivo='anexos/documento-operacao-restrita.pdf',
            descricao_anexo='ANEXO-PRIVADO-OPERACAO',
        )
        cls.manual = LancamentoManual.objects.create(
            empresa=cls.empresa, criado_por=cls.gerente, operacao='debito',
            descricao='LANCAMENTO-MANUAL-RESTRITO', valor=Decimal('10234.65'),
            data_vencimento=timezone.localdate(),
        )

    @classmethod
    def usuario(cls, nome, papel, empresa=None):
        usuario = User.objects.create_user(username=nome)
        assign_role(usuario, papel)
        if empresa is not None:
            vincular_usuario(usuario, empresa)
        return usuario

    def setUp(self):
        self.client.force_login(self.operador)
        media = TemporaryDirectory(prefix='mediata-operador-access-')
        self.addCleanup(media.cleanup)
        self.media_root = Path(media.name)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.hoje = timezone.localdate()
        self.detail_url = reverse('exibir-ticket', args=[self.ticket.key])

    def snapshot(self, *, operational=True):
        models = (
            Orcamento, ItemOrcamento, Pagamentos, Recebimentos, Anexo,
            LancamentoManual, Cliente, Colaborador, Insumos, UsuarioEmpresa,
        )
        if operational:
            models += (Ticket, SequenciaTicket, HistoricoTicket)
        return {
            model._meta.label_lower: list(model.objects.order_by('pk').values())
            for model in models
        }

    def payload_operacional(self, **alteracoes):
        payload = {
            'ticket': self.ticket.ticket, 'descricao': 'Descrição operacional atualizada',
            'status': 'E', 'data_finalizar': (self.hoje + timedelta(days=3)).isoformat(),
        }
        payload.update(alteracoes)
        return payload

    def tickets_inacessiveis(self):
        return (
            self.ticket_colega, self.ticket_gerente, self.ticket_assinante,
            self.ticket_estrangeiro, self.disponivel,
        )

    def assert_sem_financeiro(self, response):
        for segredo in (
            '91.234,56', '81.234,57', '71.234,58', '61.234,59', '51.234,60',
            '41.234,61', '31.234,62', '21.234,63', '11.234,64', '10.234,65',
            self.orcamento.orcamento, self.orcamento.descricao, self.insumo.insumo,
            self.recebimento.descricao_recebimento, self.manual.descricao,
            self.ticket.nfe_path, self.pagamento.comprovante,
            self.recebimento.comprovante_recebimento, self.anexo.arquivo.name,
            self.colaborador.banco, self.colaborador.conta, self.colaborador.chave_pix,
        ):
            with self.subTest(segredo=segredo):
                self.assertNotContains(response, segredo)
        self.assertNotContains(response, 'R$')

    def test_papeis_staff_e_grupos_mistos_nao_transformam_operador_em_gestor(self):
        for usuario, operacao, gestao in (
            (self.operador, True, False), (self.colega, True, False),
            (self.gerente, True, True), (self.superusuario, True, True),
            (self.assinante, False, False),
        ):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(pode_operar_tickets(usuario), operacao)
                self.assertEqual(pode_gerenciar_empresa(usuario), gestao)
                self.assertEqual(pode_acessar_financeiro(usuario), gestao)
        self.operador.groups.add(Group.objects.get(name='colaborador'))
        self.operador.is_staff = True
        self.operador.save(update_fields=['is_staff'])
        self.client.force_login(self.operador)
        self.assertTrue(pode_operar_tickets(self.operador))
        self.assertFalse(pode_acessar_financeiro(self.operador))
        for url in (reverse('admin:index'), reverse('financeiro:index'), reverse('index-usuarios')):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(reverse('perfil-usuario', args=[self.operador.pk])).status_code, 200)

    def test_operador_consulta_so_tickets_que_cadastrou_na_empresa_sem_dados_financeiros(self):
        listagem = self.client.get(reverse('index-tickets'))
        self.assertEqual(listagem.status_code, 200)
        self.assertEqual({item.pk for item in listagem.context['tickets']}, {
            self.ticket.pk, self.ticket_proprio.pk,
        })
        for ticket in self.tickets_inacessiveis():
            self.assertNotContains(listagem, ticket.ticket)
            self.assertNotContains(listagem, ticket.descricao)
        self.assert_sem_financeiro(listagem)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ticket.descricao)
        self.assert_sem_financeiro(response)
        self.assertFalse(response.context['pode_acessar_financeiro'])
        for chave in (
            'resumo_pagamentos', 'resumo_geral', 'valor_custo_total', 'bdi', 'margem',
            'orcamento', 'itemorcamento', 'list_pagamento', 'pagamento_form',
            'recebimentos', 'recebimentos_form', 'insumos', 'anexos',
        ):
            with self.subTest(contexto=chave):
                self.assertNotIn(chave, response.context)
        for ticket in self.tickets_inacessiveis():
            for rota in ('exibir-ticket', 'editar-ticket'):
                self.assertEqual(self.client.get(reverse(rota, args=[ticket.key])).status_code, 404)
        for parametros in ({}, {'term': self.ticket_colega.ticket}, {'q': self.ticket_gerente.ticket}):
            busca = self.client.get(reverse('buscar_tickets'), parametros)
            self.assertEqual(busca.status_code, 200)
            for ticket in self.tickets_inacessiveis():
                self.assertNotContains(busca, ticket.ticket)
                self.assertNotContains(busca, ticket.descricao)

    def test_dashboard_operacional_nao_carrega_nem_serializa_indicadores_financeiros(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['dashboard_can_view_financial'])
        metrics = response.context['dashboard_metrics']
        self.assertEqual(metrics['tickets_total'], 2)
        self.assertEqual({item.pk for item in response.context['tickets']}, {
            self.ticket.pk, self.ticket_proprio.pk,
        })
        for campo in (
            'budget_total', 'budget_month', 'paid_total', 'pending_payments',
            'receivable_total', 'received_total',
        ):
            self.assertNotIn(campo, metrics)
        charts = response.context['dashboard_charts']
        self.assertEqual(sum(item['value'] for item in charts['status']), 2)
        self.assertEqual(sum(item['tickets'] for item in charts['monthly']), 2)
        self.assertNotIn('Cliente exclusivo dos tickets de terceiros', str(charts))
        self.assertNotIn('Prestador exclusivo dos tickets de terceiros', str(charts))
        for ticket in self.tickets_inacessiveis():
            self.assertNotContains(response, ticket.ticket)
            self.assertNotContains(response, ticket.descricao)
        self.assertNotIn('histogram', charts)
        self.assertTrue(all('budget' not in item for item in charts['monthly']))
        self.assertNotIn('orcamentos', response.context)
        self.assertNotIn('total_mes', response.context)
        for item in response.context['tickets']:
            self.assertFalse(hasattr(item, 'total_orcamentos'))
            self.assertFalse(hasattr(item, 'total_pagamentos'))
        sql = '\n'.join(query['sql'].lower() for query in queries)
        for tabela in ('tickets_orcamento', 'tickets_pagamentos', 'tickets_recebimentos', 'financeiro_lancamentomanual'):
            self.assertNotIn(tabela, sql)
        self.assert_sem_financeiro(response)

    def test_urls_de_operacao_nao_permitem_consultar_ou_alterar_ticket_de_terceiro(self):
        antes = self.snapshot()
        for ticket in self.tickets_inacessiveis():
            rotas = (
                ('exibir-ticket', {'key': ticket.key}, ('get', 'post')),
                ('editar-ticket', {'key': ticket.key}, ('get', 'post')),
                ('update-historico', {'key': ticket.key}, ('get', 'post')),
                ('add-colaborador-ticket', {'id_ticket': ticket.pk}, ('get',)),
                ('add-cliente-ticket', {'id_ticket': ticket.pk}, ('get',)),
                ('cadastrar-colaborador-ticket', {
                    'id_ticket': ticket.pk, 'id_colaborador': self.colaborador.pk,
                }, ('post',)),
                ('cadastrar-cliente-ticket', {
                    'id_ticket': ticket.pk, 'id_cliente': self.cliente.pk,
                }, ('post',)),
            )
            for nome, kwargs, metodos in rotas:
                for metodo in metodos:
                    with self.subTest(ticket=ticket.ticket, rota=nome, metodo=metodo):
                        response = getattr(self.client, metodo)(reverse(nome, kwargs=kwargs), {
                            **self.payload_operacional(ticket=ticket.ticket),
                            'usuario': self.operador.pk, 'usuario_id': self.operador.pk,
                            'assumido_por': self.operador.pk, 'empresa': self.empresa.pk,
                        })
                        self.assertEqual(response.status_code, 404)
                        self.assertNotContains(response, ticket.descricao, status_code=404)
                        self.assertEqual(self.snapshot(), antes)

    def test_gerente_mantem_visao_da_empresa_e_operador_nao_herda_acesso_pela_atribuicao(self):
        self.client.force_login(self.gerente)
        response = self.client.get(reverse('index-tickets'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item.pk for item in response.context['tickets']}, {
            self.ticket.pk, self.ticket_colega.pk, self.ticket_gerente.pk,
            self.ticket_assinante.pk, self.ticket_proprio.pk,
        })
        self.assertEqual(self.client.get(reverse('exibir-ticket', args=[self.ticket_assinante.key])).status_code, 200)
        self.assertNotContains(response, self.ticket_estrangeiro.ticket)
        self.client.force_login(self.colega)
        response = self.client.get(reverse('index-tickets'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item.pk for item in response.context['tickets']}, {self.ticket_colega.pk})
        self.assertEqual(self.client.get(self.detail_url).status_code, 404)
        self.client.force_login(self.operador)
        self.assertEqual(self.client.get(reverse('exibir-ticket', args=[self.ticket_colega.key])).status_code, 404)

    @patch('tickets.views.HTML')
    def test_urls_financeiras_diretas_e_pdfs_negam_operador_sem_alteracoes(self, renderer):
        key = self.ticket.key
        routes = (
            ('financeiro:index', {}, ('get', 'post')),
            ('financeiro:novo-lancamento', {}, ('get', 'post')),
            ('financeiro:editar-manual', {'pk': self.manual.pk}, ('get', 'post')),
            ('financeiro:editar-pagamento', {'pk': self.pagamento.pk}, ('get', 'post')),
            ('financeiro:editar-recebimento', {'pk': self.recebimento.pk}, ('get', 'post')),
            ('relatorios', {}, ('get', 'post')),
            ('gerar_pdf_ticket', {'key': key}, ('get',)),
            ('gerar_pdf_orcamento', {'ticket_id': self.ticket.pk}, ('get',)),
            ('add-pagamento', {'key': key}, ('get', 'post')),
            ('editar-pagamento', {'pagamento_id': self.pagamento.pk, 'key': key}, ('get', 'post')),
            ('editar-recebimento', {'recebimento_id': self.recebimento.pk, 'key': key}, ('get', 'post')),
            ('deletar-pagamento', {'id': self.pagamento.pk, 'key': key}, ('post',)),
            ('deletar-recebimento', {'recebimento_id': self.recebimento.pk, 'key': key}, ('post',)),
            ('deletar-item', {'id': self.item.pk, 'key': key}, ('post',)),
            ('deletar-anexo', {'anexo_id': self.anexo.pk, 'key': key}, ('post',)),
            ('upload-nfe', {'key': key}, ('post',)),
            ('delete-nfe', {'key': key}, ('post',)),
            ('upload-comprovante', {'id': self.pagamento.pk, 'key': key}, ('post',)),
            ('delete-comprovante', {'id': self.pagamento.pk, 'key': key}, ('post',)),
            ('deletar-ticket', {'key': key}, ('post',)),
        )
        antes = self.snapshot()
        for nome, kwargs, methods in routes:
            for method in methods:
                with self.subTest(rota=nome, metodo=method):
                    response = getattr(self.client, method)(reverse(nome, kwargs=kwargs), {
                        'tipo': 'M', 'valor_pagamento': '999.99', 'status_pagamento': 'on',
                        'valor_recebimento': '999.99', 'status_recebimento': 'True',
                        'valor': '999.99', 'operacao': 'debito', 'descricao': 'Mudança proibida',
                        'data_vencimento': self.hoje.isoformat(), 'apresentacao': 'modal',
                    })
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(self.snapshot(), antes)
        renderer.assert_not_called()
        self.assertEqual(list(self.media_root.rglob('*')), [])

    def test_post_financeiro_forjado_no_ticket_nao_grava_nem_atualiza_status(self):
        antes = self.snapshot()
        for tipo in ('orcamento', 'itemorcamento', 'form-pagamento', 'recebimentos_form', 'anexo'):
            with self.subTest(tipo=tipo):
                response = self.client.post(self.detail_url, {
                    **self.payload_operacional(), 'form_type': tipo,
                    'orcamento-orcamento': 'Orçamento indevido',
                    'orcamento-descricao': 'Escopo indevido',
                    'item': self.insumo.pk, 'quant': '2', 'tipo': 'M',
                    'valor_pagamento': '999.99', 'data_vencimento': self.hoje.isoformat(),
                    'valor_recebimento': '999.99', 'status_recebimento': 'True',
                    'arquivo': SimpleUploadedFile('invalido.pdf', b'fixture', 'application/pdf'),
                })
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.snapshot(), antes)
        self.assertEqual(list(self.media_root.rglob('*')), [])

    def test_cadastros_configuracoes_e_usuarios_negam_acesso_por_id_e_mutacoes(self):
        rotas = (
            ('listar-clientes', {}), ('cadastrar-cliente', {}),
            ('editar-cliente', {'cliente_id': self.cliente.pk}),
            ('deletar-cliente', {'cliente_id': self.cliente.pk}),
            ('perfil_cliente', {'id': self.cliente.pk}),
            ('lista_colaboradores', {}), ('cadastrar_colaborador', {}),
            ('editar-colaborador', {'colaborador_id': self.colaborador.pk}),
            ('deletar-colaborador', {'colaborador_id': self.colaborador.pk}),
            ('perfil_colaborador', {'id': self.colaborador.pk}),
            ('criar_usuario_colaborador', {'colaborador_id': self.colaborador.pk}),
            ('index-insumos', {}), ('editar-insumos', {'id': self.insumo.pk}),
            ('deletar-insumos', {'id': self.insumo.pk}),
            ('empresa_lista', {}), ('empresa_perfil', {'pk': self.empresa.pk}),
            ('empresa_editar', {'pk': self.empresa.pk}), ('empresa_cadastrar', {}),
            ('index-usuarios', {}), ('registrar-usuarios', {}),
            ('perfil-usuario', {'id': self.gerente.pk}),
            ('editar-usuario', {'user_id': self.gerente.pk}),
            ('editar-usuarios', {'id': self.gerente.pk}),
            ('buscar-itens', {}), ('admin:index', {}),
        )
        antes = self.snapshot()
        usuarios_antes = list(User.objects.order_by('pk').values())
        for nome, kwargs in rotas:
            for metodo in ('get', 'post'):
                with self.subTest(rota=nome, metodo=metodo):
                    response = getattr(self.client, metodo)(reverse(nome, kwargs=kwargs), {
                        'nome_completo': 'Alteração proibida', 'username': 'cadastro_indevido',
                        'is_superuser': 'on', 'is_staff': 'on', 'empresa': self.outra_empresa.pk,
                    })
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(self.snapshot(), antes)
                    self.assertEqual(list(User.objects.order_by('pk').values()), usuarios_antes)

    def test_documentos_privados_negam_get_e_head_mesmo_com_caminho_conhecido(self):
        for caminho in (
            self.ticket.nfe_path, self.pagamento.comprovante,
            self.recebimento.comprovante_recebimento, self.anexo.arquivo.name,
            'nfe/inexistente.pdf',
        ):
            for metodo in ('get', 'head'):
                with self.subTest(caminho=caminho, metodo=metodo):
                    response = getattr(self.client, metodo)('/media/' + caminho)
                    self.assertEqual(response.status_code, 403)
        self.assertEqual(list(self.media_root.rglob('*')), [])

    def test_criar_e_editar_ticket_ignora_valores_e_vinculos_financeiros_forjados(self):
        financeiro_antes = self.snapshot(operational=False)
        valores_antes = {campo: getattr(self.ticket, campo) for campo in self.financial_fields}
        protegido = {
            **dict.fromkeys(self.financial_fields, '999.99'),
            'empresa': self.outra_empresa.pk, 'usuario': self.estrangeiro.pk,
            'usuario_id': self.estrangeiro.pk, 'assumido_por': self.estrangeiro.pk,
            'nfe_path': 'nfe/forjada.pdf', 'form_type': 'form-pagamento',
            'tipo': 'M', 'valor_pagamento': '999.99', 'valor_recebimento': '999.99',
        }
        response = self.client.post(reverse('cadastro-ticket'), self.payload_operacional(
            **protegido, ticket='OPNOVO001', descricao='Novo serviço operacional',
        ))
        self.assertEqual(response.status_code, 302)
        criado = Ticket.objects.get(ticket='OPNOVO001')
        self.assertEqual(criado.empresa_id, self.empresa.pk)
        self.assertEqual(criado.usuario_id, self.operador.pk)
        self.assertEqual(criado.assumido_por_id, self.operador.pk)
        self.assertFalse(criado.nfe_path)
        for campo in self.financial_fields:
            self.assertEqual(getattr(criado, campo), Ticket._meta.get_field(campo).get_default())
        response = self.client.post(reverse('editar-ticket', args=[self.ticket.key]),
                                    self.payload_operacional(**protegido))
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.descricao, 'Descrição operacional atualizada')
        self.assertEqual(self.ticket.status, 'E')
        self.assertEqual(self.ticket.empresa_id, self.empresa.pk)
        self.assertEqual(self.ticket.usuario_id, self.operador.pk)
        self.assertEqual(self.ticket.assumido_por_id, self.operador.pk)
        self.assertEqual(self.ticket.nfe_path, 'nfe/nota-operacao-restrita.pdf')
        for campo, valor in valores_antes.items():
            self.assertEqual(getattr(self.ticket, campo), valor)
        self.assertEqual(self.snapshot(operational=False), financeiro_antes)

    def test_atualizar_status_com_campos_financeiros_juntos_altera_so_operacao(self):
        financeiro_antes = self.snapshot(operational=False)
        response = self.client.post(reverse('update-historico', args=[self.ticket.key]), {
            'status': 'V', 'valor_custo': '999.99', 'valor_pagamento': '999.99',
            'form_type': 'form-pagamento', 'empresa': self.outra_empresa.pk,
            'ticket_pagamento': self.ticket_estrangeiro.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'V')
        self.assertEqual(self.ticket.valor_custo, Decimal('71234.58'))
        self.assertEqual(self.ticket.empresa_id, self.empresa.pk)
        self.assertEqual(HistoricoTicket.objects.filter(ticket_historico=self.ticket).count(), 1)
        self.assertEqual(self.snapshot(operational=False), financeiro_antes)

    def test_associar_cadastros_permite_mesma_empresa_sem_dados_bancarios_ou_alterar_catalogos(self):
        financeiro_antes = self.snapshot(operational=False)
        for nome, nome_estrangeiro in (
            ('add-colaborador-ticket', self.colaborador_estrangeiro.nome_completo),
            ('add-cliente-ticket', self.cliente_estrangeiro.nome_razao_social),
        ):
            response = self.client.get(reverse(nome, args=[self.ticket.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, nome_estrangeiro)
            self.assert_sem_financeiro(response)
        for nome, kwargs in (
            ('cadastrar-colaborador-ticket', {'id_ticket': self.ticket.pk, 'id_colaborador': self.colaborador.pk}),
            ('cadastrar-cliente-ticket', {'id_ticket': self.ticket.pk, 'id_cliente': self.cliente.pk}),
        ):
            with self.subTest(rota=nome):
                response = self.client.post(reverse(nome, kwargs=kwargs))
                self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.cliente_id, self.cliente.pk)
        self.assertEqual(self.ticket.colaborador_id, self.colaborador.pk)
        self.assertEqual(self.snapshot(operational=False), financeiro_antes)
        antes = self.snapshot()
        for nome, kwargs in (
            ('cadastrar-colaborador-ticket', {'id_ticket': self.ticket.pk, 'id_colaborador': self.colaborador_estrangeiro.pk}),
            ('cadastrar-cliente-ticket', {'id_ticket': self.ticket.pk, 'id_cliente': self.cliente_estrangeiro.pk}),
            ('cadastrar-cliente-ticket', {'id_ticket': self.ticket_estrangeiro.pk, 'id_cliente': self.cliente.pk}),
        ):
            with self.subTest(rota=nome):
                self.assertEqual(self.client.post(reverse(nome, kwargs=kwargs)).status_code, 404)
                self.assertEqual(self.snapshot(), antes)

    def test_operador_nao_acessa_fila_nem_assume_ticket_cadastrado_por_outro_usuario(self):
        antes = self.snapshot()
        for rota, kwargs, metodo in (
            ('tickets-disponiveis', {}, 'get'),
            ('ticket-disponivel', {'key': self.disponivel.key}, 'get'),
            ('assumir-ticket', {'key': self.disponivel.key}, 'post'),
        ):
            with self.subTest(rota=rota):
                response = getattr(self.client, metodo)(reverse(rota, kwargs=kwargs))
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.snapshot(), antes)

    def test_gerente_continua_assumindo_ticket_sem_alterar_financas_ou_autoria(self):
        self.client.force_login(self.gerente)
        financeiro_antes = self.snapshot(operational=False)
        self.assertContains(self.client.get(reverse('tickets-disponiveis')), self.disponivel.ticket)
        response = self.client.post(reverse('assumir-ticket', args=[self.disponivel.key]), {
            'empresa': self.outra_empresa.pk, 'valor_faturamento': '999.99',
        })
        self.assertEqual(response.status_code, 302)
        self.disponivel.refresh_from_db()
        self.assertEqual(self.disponivel.empresa_id, self.empresa.pk)
        self.assertEqual(self.disponivel.assumido_por_id, self.gerente.pk)
        self.assertEqual(self.disponivel.usuario_id, self.assinante.pk)
        self.assertEqual(self.disponivel.valor_faturamento, Decimal('1.00'))
        self.assertEqual(self.snapshot(operational=False), financeiro_antes)
        self.client.force_login(self.operador)
        self.assertEqual(self.client.get(reverse('exibir-ticket', args=[self.disponivel.key])).status_code, 404)

    def test_servico_financeiro_tambem_nega_operador_sem_depender_do_menu_ou_middleware(self):
        filtros = {'operacao': 'todas', 'situacao': 'todas', 'data_inicio': None, 'data_fim': None}
        with self.assertRaises(PermissionDenied):
            fontes_financeiras(self.operador, filtros, self.hoje)


class MigracaoPermissoesOperadorTests(TestCase):
    def test_migracao_limpa_permissoes_legadas_sem_alterar_vinculos_ou_gestores(self):
        empresa = criar_empresa('Empresa da migração de acesso', '00.000.000/0000-93')
        grupo = Group.objects.get(name='operador')
        gerente = Group.objects.get(name='gerente')
        content_type = ContentType.objects.get_for_model(User)
        proibidas = list(Permission.objects.filter(
            content_type=content_type, codename__in=('criar_insumo', 'criar_usuarios', 'ver_usuarios'),
        ))
        self.assertEqual(len(proibidas), 3)
        extra = Permission.objects.create(
            content_type=content_type, codename='permissao_customizada_operador_fixture',
            name='Permissão personalizada para teste',
        )
        grupo.permissions.add(*proibidas)
        operador = User.objects.create_user(username='legado_operador_fixture', is_staff=True)
        gestor = User.objects.create_user(username='legado_gestor_fixture')
        admin = User.objects.create_superuser(username='legado_admin_fixture', email='', password=None)
        for usuario in (operador, gestor, admin):
            usuario.groups.add(grupo)
            usuario.user_permissions.add(*proibidas, extra)
            vincular_usuario(usuario, empresa)
        gestor.groups.add(gerente)
        grupos_antes = list(User.groups.through.objects.order_by('pk').values())
        empresas_antes = list(UsuarioEmpresa.objects.order_by('pk').values())
        ids_grupos_antes = list(Group.objects.order_by('pk').values('id', 'name'))
        migracao = import_module('usuarios.migrations.0005_restringir_permissoes_operador')
        historical_apps = ProjectState.from_apps(apps).apps
        for _ in range(2):
            migracao.restringir_permissoes_operador(historical_apps, connection.schema_editor())
        self.assertFalse(grupo.permissions.filter(pk__in=[p.pk for p in proibidas]).exists())
        self.assertFalse(operador.user_permissions.filter(pk__in=[p.pk for p in proibidas]).exists())
        self.assertTrue(operador.user_permissions.filter(pk=extra.pk).exists())
        for usuario in (gestor, admin):
            self.assertEqual(set(usuario.user_permissions.values_list('pk', flat=True)), {
                *(permissao.pk for permissao in proibidas), extra.pk,
            })
        self.assertEqual(list(User.groups.through.objects.order_by('pk').values()), grupos_antes)
        self.assertEqual(list(UsuarioEmpresa.objects.order_by('pk').values()), empresas_antes)
        self.assertEqual(list(Group.objects.order_by('pk').values('id', 'name')), ids_grupos_antes)
