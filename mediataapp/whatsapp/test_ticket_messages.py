"""Mensagens de ticket são confirmadas, isoladas e sempre simuladas nos testes."""

import time
from datetime import timedelta
from decimal import Decimal
from queue import Queue
from threading import Event, Thread
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rolepermissions.roles import assign_role

from clientes.models import Cliente
from colaborador.models import Colaborador
from tickets.models import Anexo, HistoricoTicket, Orcamento, Pagamentos, Recebimentos, Ticket
from usuarios.test_helpers import criar_empresa, vincular_usuario
from .client import EvolutionError
from .models import ConexaoWhatsApp, EnvioTicketWhatsApp


WHATSAPP_SETTINGS = {
    'EVOLUTION_ENABLED': True,
    'EVOLUTION_API_URL': 'https://evolution.example.invalid/private-ticket-root',
    'EVOLUTION_API_KEY': 'chave-ficticia-de-envio-de-ticket',
    'EVOLUTION_WEBHOOK_BASE_URL': 'https://mediata.example.invalid',
    'EVOLUTION_API_TIMEOUT': 7,
    'SECRET_KEY': 'assinatura-de-confirmacao-apenas-para-teste',
}


@override_settings(**WHATSAPP_SETTINGS)
class TicketWhatsAppTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = criar_empresa('Envios de teste A', '00.000.000/0000-51')
        cls.outra_empresa = criar_empresa('Envios de teste B', '00.000.000/0000-52')
        cls.operador = cls.usuario('operador_envio_ticket', 'operador', cls.empresa)
        cls.gerente = cls.usuario('gerente_envio_ticket', 'gerente', cls.empresa)
        cls.outro_gerente = cls.usuario('gerente_envio_estrangeiro', 'gerente', cls.outra_empresa)
        cls.colaborador_user = cls.usuario('colaborador_envio_ticket', 'colaborador', cls.empresa)
        cls.cliente_user = cls.usuario('cliente_envio_ticket', 'cliente', cls.empresa)
        cls.assinante = cls.usuario('assinante_envio_ticket', 'assinante')
        cls.admin = User.objects.create_superuser(
            username='admin_envio_ticket', email='admin-envio@example.invalid', password=None,
        )
        cls.responsavel = Colaborador.objects.create(
            empresa=cls.empresa, nome_completo='Prestador fictício do ticket',
            telefone='11999990001', ativo=True,
        )
        cls.outro_responsavel = Colaborador.objects.create(
            empresa=cls.outra_empresa, nome_completo='Prestador privado da empresa B',
            telefone='21999990002', ativo=True,
        )
        cls.cliente = Cliente.objects.create(
            empresa=cls.empresa, nome_razao_social='CLIENTE-PRIVADO-NAO-COMPARTILHAR',
            cpf_cnpj='00000000051', endereco='ENDERECO-PRIVADO-NAO-COMPARTILHAR',
        )
        cls.previsao = timezone.localdate() + timedelta(days=3)
        cls.ticket = Ticket.objects.create(
            ticket='WATST001', empresa=cls.empresa, usuario=cls.operador,
            assumido_por=cls.gerente, colaborador=cls.responsavel, cliente=cls.cliente,
            descricao='Trocar peça da sala técnica.\nInspecionar acabamento.',
            status='E', emergencial=True, data_finalizar=cls.previsao,
            valor_custo=Decimal('98765.43'), nfe_path='nfe/documento-privado-de-envio.pdf',
        )
        cls.ticket_colega = Ticket.objects.create(
            ticket='WATST002', empresa=cls.empresa, usuario=cls.gerente,
            assumido_por=cls.operador, colaborador=cls.responsavel,
            descricao='Ticket de terceiro da mesma empresa',
        )
        cls.ticket_estrangeiro = Ticket.objects.create(
            ticket='WATST003', empresa=cls.outra_empresa, usuario=cls.operador,
            colaborador=cls.outro_responsavel, descricao='Ticket privado de outra empresa',
        )
        cls.conexao = ConexaoWhatsApp.objects.create(
            empresa=cls.empresa, instancia_criada=True,
            estado=ConexaoWhatsApp.Estado.CONECTADO, webhook_secret='f' * 64,
        )
        ConexaoWhatsApp.objects.create(
            empresa=cls.outra_empresa, instancia_criada=True,
            estado=ConexaoWhatsApp.Estado.CONECTADO,
        )
        Orcamento.objects.create(
            ticket_orcamento=cls.ticket, orcamento='ORCAMENTO-PRIVADO-DE-ENVIO',
            descricao='Escopo comercial privado', valor_total=Decimal('87654.32'),
        )
        Pagamentos.objects.create(
            ticket_pagamento=cls.ticket, tipo='M', valor_pagamento=Decimal('76543.21'),
        )
        Recebimentos.objects.create(
            ticket_recebimento=cls.ticket, valor_recebimento=Decimal('65432.10'),
        )
        Anexo.objects.create(
            ticket_anexo=cls.ticket, arquivo='anexos/documento-privado-de-envio.pdf',
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
        bloqueio = patch('requests.request', side_effect=AssertionError('Envios reais são proibidos nos testes.'))
        self.http = bloqueio.start()
        self.addCleanup(bloqueio.stop)
        fabrica = patch('whatsapp.ticket_services.EvolutionClient')
        self.provider_factory = fabrica.start()
        self.addCleanup(fabrica.stop)
        self.provider = self.provider_factory.return_value
        self.provider.estado_instancia.return_value = {
            'instance': {'instanceName': self.conexao.nome_instancia, 'state': 'open'},
        }
        self.provider.enviar_texto.return_value = {
            'key': {'id': 'ID-ACEITO-FICTICIO', 'remoteJid': '5511999990001@s.whatsapp.net'},
            'status': 'PENDING', 'apikey': settings.EVOLUTION_API_KEY,
        }

    def url(self, nome, ticket=None):
        return reverse(f'ticket-whatsapp-{nome}', kwargs={'key': (ticket or self.ticket).key})

    def previa(self, ticket=None, client=None):
        response = (client or self.client).get(self.url('previa', ticket))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        return response

    def enviar(self, token, ticket=None, **alteracoes):
        return self.client.post(self.url('enviar', ticket), {
            'confirmacao': token, **alteracoes,
        })

    def snapshot_ticket(self):
        models = (Ticket, HistoricoTicket, Colaborador, Orcamento, Pagamentos, Recebimentos, Anexo)
        return {
            model._meta.label_lower: list(model.objects.order_by('pk').values())
            for model in models
        }

    def assert_sem_segredos(self, response):
        for segredo in (
            settings.EVOLUTION_API_KEY, settings.EVOLUTION_API_URL,
            self.conexao.nome_instancia, self.conexao.webhook_secret,
            '5511999990001', '11999990001', 'ID-ACEITO-FICTICIO',
        ):
            self.assertNotIn(segredo, response.content.decode())
        self.assertIn('no-store', response['Cache-Control'])

    def test_previa_so_contem_os_cinco_campos_atuais_e_destinatario_mascarado_sem_efeitos(self):
        antes = self.snapshot_ticket()
        response = self.previa()
        dados = response.json()
        self.assertEqual(set(dados), {
            'ok', 'numero_ticket', 'destinatario', 'mensagem', 'confirmacao', 'ultimo_envio',
        })
        self.assertEqual(dados['numero_ticket'], self.ticket.ticket)
        self.assertEqual(set(dados['destinatario']), {'nome', 'telefone_mascarado'})
        self.assertEqual(dados['destinatario']['nome'], self.responsavel.nome_completo)
        self.assertIn('0001', dados['destinatario']['telefone_mascarado'])
        self.assertIsNone(dados['ultimo_envio'])
        self.assertTrue(dados['confirmacao'])
        for campo in (
            self.ticket.ticket, self.ticket.get_status_display(),
            self.previsao.strftime('%d/%m/%Y'), self.ticket.descricao, 'Sim',
        ):
            self.assertIn(campo, dados['mensagem'])
        for privado in (
            '98765.43', '98.765,43', '87654.32', '87.654,32', '76.543,21', '65.432,10',
            'ORCAMENTO-PRIVADO-DE-ENVIO', self.cliente.nome_razao_social, self.cliente.endereco,
            self.ticket.nfe_path, 'anexos/documento-privado-de-envio.pdf', 'R$',
        ):
            self.assertNotIn(privado, dados['mensagem'])
        self.assert_sem_segredos(response)
        self.assertEqual(self.snapshot_ticket(), antes)
        self.assertFalse(EnvioTicketWhatsApp.objects.exists())
        self.provider.estado_instancia.assert_not_called()
        self.provider.enviar_texto.assert_not_called()
        self.http.assert_not_called()

    def test_usuarios_sem_permissao_e_tickets_de_terceiros_nao_fazem_previa_ou_envio(self):
        antes = self.snapshot_ticket()
        for usuario, ticket, esperado in (
            (self.colaborador_user, self.ticket, 403), (self.cliente_user, self.ticket, 403),
            (self.assinante, self.ticket, 403), (self.operador, self.ticket_colega, 404),
            (self.operador, self.ticket_estrangeiro, 404), (self.outro_gerente, self.ticket, 404),
        ):
            self.client.force_login(usuario)
            for nome, metodo in (('previa', 'get'), ('enviar', 'post')):
                with self.subTest(usuario=usuario.username, ticket=ticket.ticket, rota=nome):
                    response = getattr(self.client, metodo)(self.url(nome, ticket), {'confirmacao': 'forjada'})
                    self.assertEqual(response.status_code, esperado)
        self.assertEqual(self.snapshot_ticket(), antes)
        self.assertFalse(EnvioTicketWhatsApp.objects.exists())
        self.provider_factory.assert_not_called()
        self.http.assert_not_called()

    def test_metodos_csrf_e_login_protegem_envio(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url('previa')).status_code, 302)
        self.assertEqual(self.client.post(self.url('enviar')).status_code, 302)
        self.client.force_login(self.operador)
        self.assertEqual(self.client.post(self.url('previa')).status_code, 405)
        self.assertEqual(self.client.get(self.url('enviar')).status_code, 405)
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.operador)
        token = self.previa(client=protegido).json()['confirmacao']
        response = protegido.post(self.url('enviar'), {'confirmacao': token})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(EnvioTicketWhatsApp.objects.exists())
        self.provider.enviar_texto.assert_not_called()

    def test_envio_confirmado_usa_snapshot_do_servidor_e_auditoria_minima(self):
        antes = self.snapshot_ticket()
        previa = self.previa().json()
        response = self.enviar(previa['confirmacao'],
            telefone='+12025550199', number='+12025550199', destinatario=self.outro_responsavel.pk,
            texto='TEXTO-FORJADO', mensagem='TEXTO-FORJADO', empresa=self.outra_empresa.pk,
        )
        self.assertEqual(response.status_code, 200)
        dados = response.json()
        self.assertEqual(set(dados), {'ok', 'mensagem', 'estado', 'envio_id', 'ultimo_envio'})
        self.assertTrue(dados['ok'])
        self.assertEqual(dados['estado'], 'aceito')
        self.assert_sem_segredos(response)
        self.provider.estado_instancia.assert_called_once_with(self.conexao.nome_instancia)
        self.provider.enviar_texto.assert_called_once_with(
            self.conexao.nome_instancia, '5511999990001', previa['mensagem'],
        )
        registro = EnvioTicketWhatsApp.objects.get()
        self.assertEqual(str(registro.pk), str(dados['envio_id']))
        self.assertEqual(registro.empresa_id, self.empresa.pk)
        self.assertEqual(registro.ticket_id, self.ticket.pk)
        self.assertEqual(registro.colaborador_id, self.responsavel.pk)
        self.assertEqual(registro.usuario_id, self.operador.pk)
        self.assertEqual(registro.estado, 'aceito')
        self.assertIsNotNone(registro.finalizado_em)
        registro_texto = str(EnvioTicketWhatsApp.objects.values().get())
        for privado in ('5511999990001', '11999990001', previa['mensagem'], settings.EVOLUTION_API_KEY):
            self.assertNotIn(privado, registro_texto)
        self.assertEqual(self.snapshot_ticket(), antes)
        historico = self.previa().json()['ultimo_envio']
        self.assertEqual(set(historico), {'estado', 'mensagem', 'criado_em', 'usuario'})
        self.assertEqual(historico['estado'], 'aceito')
        self.http.assert_not_called()

    def test_gerente_e_administrador_podem_previsualizar_ticket_de_outro_autor(self):
        for usuario in (self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                response = self.previa(self.ticket_colega)
                self.assertEqual(response.json()['numero_ticket'], self.ticket_colega.ticket)
        self.provider.estado_instancia.assert_not_called()
        self.provider.enviar_texto.assert_not_called()
        self.assertFalse(EnvioTicketWhatsApp.objects.exists())

    def test_alterar_snapshot_apos_previa_exige_nova_confirmacao_sem_enviar(self):
        originais = {
            'ticket': self.ticket.ticket, 'status': self.ticket.status,
            'data_finalizar': self.ticket.data_finalizar, 'descricao': self.ticket.descricao,
            'emergencial': self.ticket.emergencial,
        }
        alteracoes = (
            {'ticket': 'WATST009'}, {'status': 'V'},
            {'data_finalizar': self.previsao + timedelta(days=1)},
            {'descricao': 'Descrição alterada depois da confirmação'}, {'emergencial': False},
        )
        for mudanca in alteracoes:
            with self.subTest(mudanca=mudanca):
                Ticket.objects.filter(pk=self.ticket.pk).update(**originais)
                token = self.previa().json()['confirmacao']
                Ticket.objects.filter(pk=self.ticket.pk).update(**mudanca)
                response = self.enviar(token)
                self.assertEqual(response.status_code, 409)
                self.assertFalse(response.json()['ok'])
                self.assertFalse(EnvioTicketWhatsApp.objects.exists())
                self.provider.estado_instancia.assert_not_called()
                self.provider.enviar_texto.assert_not_called()
        self.http.assert_not_called()

    def test_mesmo_token_inclusive_expirado_reaproveita_envio_aceito_sem_duplicar(self):
        momento = time.time()
        token = self.previa().json()['confirmacao']
        primeiro = self.enviar(token)
        self.assertEqual(primeiro.status_code, 200)
        chamadas_antes = self.provider_factory.call_count
        self.provider_factory.side_effect = EvolutionError('unavailable')
        with override_settings(EVOLUTION_ENABLED=False), patch(
            'django.core.signing.time.time', return_value=momento + 600,
        ):
            segundo = self.enviar(token)
        self.assertEqual(segundo.status_code, 200)
        self.assertEqual(segundo.json()['envio_id'], primeiro.json()['envio_id'])
        self.assertEqual(segundo.json()['estado'], 'aceito')
        self.assertEqual(EnvioTicketWhatsApp.objects.count(), 1)
        self.provider.enviar_texto.assert_called_once()
        self.provider.estado_instancia.assert_called_once()
        self.assertEqual(self.provider_factory.call_count, chamadas_antes)
        self.http.assert_not_called()

    def test_duas_abas_com_confirmacoes_distintas_nao_duplicam_envio_no_cooldown(self):
        primeira = self.previa().json()['confirmacao']
        segunda = self.previa().json()['confirmacao']
        self.assertNotEqual(primeira, segunda)
        self.assertEqual(self.enviar(primeira).status_code, 200)
        response = self.enviar(segunda)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(EnvioTicketWhatsApp.objects.count(), 1)
        self.provider.enviar_texto.assert_called_once()
        self.provider.estado_instancia.assert_called_once()

    def test_timeout_e_erro_5xx_de_envio_ficam_incertos_e_nao_sao_repetidos_automaticamente(self):
        for erro in (
            EvolutionError('timeout'), EvolutionError(provider_status=408),
            EvolutionError(provider_status=503),
        ):
            with self.subTest(codigo=erro.code, status=erro.provider_status):
                EnvioTicketWhatsApp.objects.all().delete()
                self.provider.reset_mock()
                self.provider.enviar_texto.side_effect = erro
                token = self.previa().json()['confirmacao']
                response = self.enviar(token)
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json()['estado'], 'incerto')
                self.assert_sem_segredos(response)
                registro = EnvioTicketWhatsApp.objects.get()
                self.assertEqual(registro.estado, 'incerto')
                repetido = self.enviar(token)
                self.assertEqual(repetido.json()['estado'], 'incerto')
                self.assertEqual(str(repetido.json()['envio_id']), str(registro.pk))
                self.assertEqual(EnvioTicketWhatsApp.objects.count(), 1)
                self.provider.enviar_texto.assert_called_once()
        self.http.assert_not_called()

    def test_rejeicao_4xx_conhecida_fica_falha_sem_expor_detalhes_do_provider(self):
        self.provider.enviar_texto.side_effect = EvolutionError(provider_status=400)
        token = self.previa().json()['confirmacao']
        response = self.enviar(token)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['estado'], 'falhou')
        self.assertEqual(EnvioTicketWhatsApp.objects.get().estado, 'falhou')
        self.assert_sem_segredos(response)
        self.provider.enviar_texto.assert_called_once()
        self.http.assert_not_called()

    def test_conexao_fechada_na_consulta_do_provider_nao_envia_texto(self):
        self.provider.estado_instancia.return_value = {
            'instance': {'instanceName': self.conexao.nome_instancia, 'state': 'close'},
        }
        token = self.previa().json()['confirmacao']
        response = self.enviar(token)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['ok'])
        self.provider.enviar_texto.assert_not_called()
        self.http.assert_not_called()

    def test_telefone_brasileiro_fixo_e_ddi_explicito_sao_normalizados_sem_destino_do_post(self):
        for indice, (telefone, esperado) in enumerate((
            ('(11) 3333-4444', '551133334444'),
            ('+1 202-555-0100', '12025550100'),
        ), start=1):
            with self.subTest(telefone=telefone):
                Colaborador.objects.filter(pk=self.responsavel.pk).update(telefone=telefone)
                ticket = Ticket.objects.create(
                    ticket=f'WATEL00{indice}', empresa=self.empresa, usuario=self.operador,
                    colaborador=self.responsavel, descricao='Atendimento com telefone fictício',
                )
                token = self.previa(ticket).json()['confirmacao']
                response = self.enviar(token, ticket, telefone='5511999999999')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.provider.enviar_texto.call_args.args[1], esperado)
                self.assertNotIn(esperado, response.content.decode())
        self.http.assert_not_called()

    def test_responsavel_empresa_telefone_e_conexao_validos_sao_revalidados_no_servidor(self):
        token = self.previa().json()['confirmacao']
        casos = (
            (lambda: Colaborador.objects.filter(pk=self.responsavel.pk).update(telefone='12345'), 400),
            (lambda: Ticket.objects.filter(pk=self.ticket.pk).update(colaborador=None), 409),
            (lambda: Colaborador.objects.filter(pk=self.responsavel.pk).update(ativo=False), 409),
            (lambda: Colaborador.objects.filter(pk=self.responsavel.pk).update(empresa=self.outra_empresa), 409),
            (lambda: ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).update(instancia_criada=False), 503),
            (lambda: self.empresa.__class__.objects.filter(pk=self.empresa.pk).update(ativo=False), 403),
            (lambda: ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).delete(), 503),
        )
        for indice, (alterar, status) in enumerate(casos):
            with self.subTest(caso=indice):
                self.empresa.__class__.objects.filter(pk=self.empresa.pk).update(ativo=True)
                Ticket.objects.filter(pk=self.ticket.pk).update(colaborador=self.responsavel)
                Colaborador.objects.filter(pk=self.responsavel.pk).update(
                    telefone='11999990001', ativo=True, empresa=self.empresa,
                )
                ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).update(
                    instancia_criada=True, estado=ConexaoWhatsApp.Estado.CONECTADO,
                )
                alterar()
                self.assertEqual(self.client.get(self.url('previa')).status_code, status)
                self.assertEqual(self.enviar(token).status_code, status)
                self.assertFalse(EnvioTicketWhatsApp.objects.exists())
        self.provider.enviar_texto.assert_not_called()
        self.provider.estado_instancia.assert_not_called()
        self.http.assert_not_called()

    def test_confirmacao_ausente_adulterada_expirada_ou_transferida_nao_autoriza_envio(self):
        momento = time.time()
        token = self.previa().json()['confirmacao']
        for invalida in ('', 'assinatura-invalida', token + 'modificado', 'x' * 3000):
            with self.subTest(token=invalida[:20]):
                self.assertEqual(self.enviar(invalida).status_code, 400)
        with patch('django.core.signing.time.time', return_value=momento + 301):
            self.assertEqual(self.enviar(token).status_code, 400)
        outro_ticket = Ticket.objects.create(
            ticket='WATOK001', empresa=self.empresa, usuario=self.operador,
            colaborador=self.responsavel, descricao='Outro ticket do mesmo autor',
        )
        self.assertEqual(self.enviar(token, outro_ticket).status_code, 400)
        self.client.force_login(self.gerente)
        self.assertEqual(self.enviar(token).status_code, 400)
        self.assertFalse(EnvioTicketWhatsApp.objects.exists())
        self.provider.estado_instancia.assert_not_called()
        self.provider.enviar_texto.assert_not_called()
        self.http.assert_not_called()

    def test_responsavel_alterado_durante_consulta_de_conexao_impede_envio_ao_numero_antigo(self):
        token = self.previa().json()['confirmacao']

        def estado_com_mudanca(nome):
            Colaborador.objects.filter(pk=self.responsavel.pk).update(telefone='21999990002')
            return {'instance': {'instanceName': nome, 'state': 'open'}}

        self.provider.estado_instancia.side_effect = estado_com_mudanca
        response = self.enviar(token)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['estado'], 'falhou')
        self.assertEqual(EnvioTicketWhatsApp.objects.get().estado, 'falhou')
        self.provider.enviar_texto.assert_not_called()
        self.http.assert_not_called()

    def test_resposta_sem_identificador_valido_fica_incerta_sem_retry(self):
        self.provider.enviar_texto.return_value = {'status': 'PENDING', 'key': {}}
        token = self.previa().json()['confirmacao']
        response = self.enviar(token)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['estado'], 'incerto')
        self.assertEqual(EnvioTicketWhatsApp.objects.get().estado, 'incerto')
        self.assertEqual(self.enviar(token).status_code, 409)
        self.provider.enviar_texto.assert_called_once()
        self.http.assert_not_called()

    def test_falha_ao_persistir_resultado_nao_libera_reenvio_automatico(self):
        token = self.previa().json()['confirmacao']
        with patch('whatsapp.ticket_services._finalizar_envio', return_value=None):
            response = self.enviar(token)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['estado'], 'incerto')
        registro = EnvioTicketWhatsApp.objects.get()
        self.assertEqual(registro.estado, 'processando')
        repetido = self.enviar(token)
        self.assertEqual(repetido.status_code, 409)
        self.assertEqual(repetido.json()['estado'], 'processando')
        self.provider.enviar_texto.assert_called_once()
        self.assertEqual(EnvioTicketWhatsApp.objects.count(), 1)
        self.http.assert_not_called()

    def test_processamento_abandonado_aparece_incerto_no_get_e_e_recuperado_sem_reenvio(self):
        token = self.previa().json()['confirmacao']
        self.assertEqual(self.enviar(token).status_code, 200)
        registro = EnvioTicketWhatsApp.objects.get()
        EnvioTicketWhatsApp.objects.filter(pk=registro.pk).update(
            estado='processando', atualizado_em=timezone.now() - timedelta(minutes=6),
            finalizado_em=None, id_provedor='', codigo_resultado='',
        )
        self.provider.reset_mock()
        antes = EnvioTicketWhatsApp.objects.values().get()
        previa = self.previa().json()
        self.assertEqual(previa['ultimo_envio']['estado'], 'incerto')
        self.assertEqual(EnvioTicketWhatsApp.objects.values().get(), antes)
        response = self.enviar(previa['confirmacao'])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['estado'], 'incerto')
        registro.refresh_from_db()
        self.assertEqual(registro.estado, 'incerto')
        self.assertIsNotNone(registro.finalizado_em)
        self.assertEqual(EnvioTicketWhatsApp.objects.count(), 1)
        self.provider.estado_instancia.assert_not_called()
        self.provider.enviar_texto.assert_not_called()
        self.http.assert_not_called()


@skipUnless(connection.vendor == 'postgresql', 'Concorrência real exige PostgreSQL.')
@override_settings(**WHATSAPP_SETTINGS)
class TicketWhatsAppConcorrenciaTests(TransactionTestCase):
    def test_mesma_confirmacao_em_duas_conexoes_gera_um_unico_envio(self):
        empresa = criar_empresa('Envio concorrente fictício', '00.000.000/0000-53')
        usuario = User.objects.create_user(username='operador_envio_concorrente')
        assign_role(usuario, 'operador')
        vincular_usuario(usuario, empresa)
        colaborador = Colaborador.objects.create(
            empresa=empresa, nome_completo='Prestador concorrência fictícia', telefone='11999990001',
        )
        ticket = Ticket.objects.create(
            ticket='WACON001', empresa=empresa, usuario=usuario, colaborador=colaborador,
            descricao='Atendimento fictício para disputa de confirmação',
        )
        conexao = ConexaoWhatsApp.objects.create(
            empresa=empresa, instancia_criada=True, estado=ConexaoWhatsApp.Estado.CONECTADO,
        )
        previa_url = reverse('ticket-whatsapp-previa', kwargs={'key': ticket.key})
        enviar_url = reverse('ticket-whatsapp-enviar', kwargs={'key': ticket.key})
        iniciou = Event()
        liberar = Event()
        resultados = Queue()

        def enviar_fake(nome, numero, texto):
            iniciou.set()
            if not liberar.wait(timeout=12):
                raise TimeoutError('O teste não liberou o transporte simulado.')
            return {'key': {'id': 'ACEITO_CONCORRENTE'}, 'status': 'PENDING'}

        def enviar(label, token):
            database = connections['default']
            database.close()
            try:
                with database.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '3s'")
                    cursor.execute("SET statement_timeout = '6s'")
                client = Client()
                client.force_login(User.objects.get(pk=usuario.pk))
                response = client.post(enviar_url, {'confirmacao': token})
                resultados.put((label, response.status_code, response.json()))
            except Exception as erro:
                resultados.put((label, 'erro', type(erro).__name__))
            finally:
                database.close()

        with patch('requests.request', side_effect=AssertionError('Não enviar mensagens reais.')) as http:
            with patch('whatsapp.ticket_services.EvolutionClient') as fabrica:
                provider = fabrica.return_value
                provider.estado_instancia.return_value = {
                    'instance': {'instanceName': conexao.nome_instancia, 'state': 'open'},
                }
                provider.enviar_texto.side_effect = enviar_fake
                self.client.force_login(usuario)
                previa = self.client.get(previa_url)
                self.assertEqual(previa.status_code, 200)
                token = previa.json()['confirmacao']
                primeira = Thread(target=enviar, args=('primeira', token), daemon=True)
                segunda = None
                primeira.start()
                try:
                    self.assertTrue(iniciou.wait(timeout=5), 'O primeiro envio não alcançou o transporte simulado.')
                    segunda = Thread(target=enviar, args=('segunda', token), daemon=True)
                    segunda.start()
                    segunda.join(timeout=7)
                    self.assertFalse(segunda.is_alive(), 'O segundo POST ficou bloqueado durante o HTTP do primeiro.')
                finally:
                    liberar.set()
                    primeira.join(timeout=8)
                    if segunda is not None:
                        segunda.join(timeout=8)
                self.assertFalse(primeira.is_alive())
                self.assertIsNotNone(segunda)
                self.assertFalse(segunda.is_alive())
                responses = {nome: (status, dados) for nome, status, dados in list(resultados.queue)}
                self.assertEqual(set(responses), {'primeira', 'segunda'}, responses)
                self.assertEqual(responses['primeira'][0], 200, responses)
                self.assertEqual(responses['segunda'][0], 409, responses)
                self.assertEqual(responses['segunda'][1]['estado'], 'processando')
                self.assertEqual(responses['primeira'][1]['envio_id'], responses['segunda'][1]['envio_id'])
                self.assertEqual(EnvioTicketWhatsApp.objects.count(), 1)
                self.assertEqual(EnvioTicketWhatsApp.objects.get().estado, 'aceito')
                provider.enviar_texto.assert_called_once()
                provider.estado_instancia.assert_called_once()
                http.assert_not_called()
