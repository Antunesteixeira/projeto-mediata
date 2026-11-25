"""Configuração do WhatsApp respeita a gestão e o isolamento das empresas."""

from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rolepermissions.roles import assign_role

from usuarios.test_helpers import criar_empresa, vincular_usuario
from .client import EvolutionError
from .models import ConexaoWhatsApp


@override_settings(
    EVOLUTION_ENABLED=True,
    EVOLUTION_API_URL='https://evolution.example.invalid/private-root',
    EVOLUTION_API_KEY='chave-de-api-apenas-para-teste',
    EVOLUTION_WEBHOOK_BASE_URL='https://mediata.example.invalid',
    EVOLUTION_API_TIMEOUT=7,
)
class WhatsAppFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = criar_empresa('WhatsApp de teste A', '00.000.000/0000-61')
        cls.outra_empresa = criar_empresa('WhatsApp de teste B', '00.000.000/0000-62')
        cls.empresa_nova = criar_empresa('WhatsApp ainda sem conexão', '00.000.000/0000-63')
        cls.empresa_inativa = criar_empresa(
            'WhatsApp de empresa inativa', '00.000.000/0000-64', ativa=False,
        )
        cls.gerente = cls.usuario('gerente_whatsapp_a', 'gerente', cls.empresa)
        cls.outro_gerente = cls.usuario('gerente_whatsapp_b', 'gerente', cls.outra_empresa)
        cls.operador = cls.usuario('operador_whatsapp', 'operador', cls.empresa)
        cls.colaborador = cls.usuario('colaborador_whatsapp', 'colaborador', cls.empresa)
        cls.cliente = cls.usuario('cliente_whatsapp', 'cliente', cls.empresa)
        cls.assinante = cls.usuario('assinante_whatsapp', 'assinante')
        cls.sem_empresa = cls.usuario('gerente_whatsapp_sem_empresa', 'gerente')
        cls.inativo = cls.usuario('gerente_whatsapp_inativo', 'gerente', cls.empresa_inativa)
        cls.admin = User.objects.create_superuser(
            username='admin_whatsapp', email='admin-whatsapp@example.invalid', password=None,
        )
        cls.conexao = ConexaoWhatsApp.objects.create(
            empresa=cls.empresa, webhook_secret='a' * 64,
        )
        cls.outra_conexao = ConexaoWhatsApp.objects.create(
            empresa=cls.outra_empresa, webhook_secret='b' * 64,
        )

    @classmethod
    def usuario(cls, nome, papel, empresa=None):
        usuario = User.objects.create_user(username=nome)
        assign_role(usuario, papel)
        if empresa is not None:
            vincular_usuario(usuario, empresa)
        return usuario

    def setUp(self):
        self.client.force_login(self.gerente)
        transporte = patch('requests.request', side_effect=AssertionError('Não consultar serviços reais nos testes.'))
        self.http = transporte.start()
        self.addCleanup(transporte.stop)

    def url(self, nome, empresa=None):
        if nome == 'index':
            return reverse('whatsapp:index')
        return reverse(f'whatsapp:{nome}', kwargs={'empresa_id': (empresa or self.empresa).pk})

    def snapshot(self):
        return list(ConexaoWhatsApp.objects.order_by('pk').values())

    def assert_sem_segredos(self, response):
        conteudo = response.content.decode()
        for segredo in (
            settings.EVOLUTION_API_KEY, settings.EVOLUTION_API_URL,
            self.conexao.nome_instancia, self.outra_conexao.nome_instancia,
            str(self.conexao.identificador), str(self.outra_conexao.identificador),
            self.conexao.webhook_secret, self.outra_conexao.webhook_secret,
        ):
            with self.subTest(segredo=segredo):
                self.assertNotIn(segredo, conteudo)


class WhatsAppAccessTests(WhatsAppFixtures):
    def test_anonimo_precisa_entrar_para_consultar_e_configurar(self):
        self.client.logout()
        for nome, metodo in (
            ('index', 'get'), ('configurar', 'get'), ('status', 'get'),
            ('conectar', 'post'), ('desconectar', 'post'),
        ):
            with self.subTest(rota=nome):
                response = getattr(self.client, metodo)(self.url(nome))
                self.assertEqual(response.status_code, 302)
                self.assertIn('/accounts/login/', response.url)
        self.http.assert_not_called()

    def test_operador_demais_perfis_e_empresa_inativa_nao_configuram_whatsapp(self):
        antes = self.snapshot()
        for usuario in (
            self.operador, self.colaborador, self.cliente,
            self.assinante, self.sem_empresa, self.inativo,
        ):
            self.client.force_login(usuario)
            for nome, metodo in (
                ('index', 'get'), ('configurar', 'get'), ('status', 'get'),
                ('conectar', 'post'), ('desconectar', 'post'),
            ):
                with self.subTest(usuario=usuario.username, rota=nome):
                    response = getattr(self.client, metodo)(self.url(nome))
                    self.assertEqual(response.status_code, 403)
                    self.assert_sem_segredos(response)
        self.assertEqual(self.snapshot(), antes)
        self.http.assert_not_called()

    def test_staff_e_grupo_adicional_de_leitura_nao_promovem_operador(self):
        self.operador.is_staff = True
        self.operador.save(update_fields=['is_staff'])
        self.operador.groups.add(Group.objects.get(name='colaborador'))
        self.client.force_login(self.operador)
        self.assertEqual(self.client.get(self.url('index')).status_code, 403)
        self.assertEqual(self.client.post(self.url('conectar')).status_code, 403)
        self.http.assert_not_called()

    def test_gerente_nao_descobre_ou_modifica_conexao_de_outra_empresa_por_id(self):
        antes = self.snapshot()
        for nome, metodo in (
            ('configurar', 'get'), ('status', 'get'), ('conectar', 'post'), ('desconectar', 'post'),
        ):
            with self.subTest(rota=nome):
                response = getattr(self.client, metodo)(self.url(nome, self.outra_empresa), {
                    'empresa': self.empresa.pk, 'empresa_id': self.empresa.pk,
                    'instanceName': self.conexao.nome_instancia,
                })
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(self.outra_empresa.nome_fantasia, response.content.decode())
                self.assert_sem_segredos(response)
        self.assertEqual(self.snapshot(), antes)
        self.http.assert_not_called()

    def test_get_da_configuracao_preserva_banco_e_nao_consulta_provider(self):
        antes = self.snapshot()
        for nome in ('index', 'configurar'):
            with self.subTest(rota=nome):
                response = self.client.get(self.url(nome))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.empresa.nome_fantasia)
                self.assertNotContains(response, self.outra_empresa.nome_fantasia)
                self.assert_sem_segredos(response)
        self.assertEqual(self.snapshot(), antes)
        self.http.assert_not_called()

    def test_superusuario_configura_empresas_ativas_sem_criar_registro_no_get(self):
        self.client.force_login(self.admin)
        antes = self.snapshot()
        response = self.client.get(self.url('index'))
        self.assertEqual(response.status_code, 200)
        for empresa in (self.empresa, self.outra_empresa, self.empresa_nova):
            self.assertContains(response, empresa.nome_fantasia)
        self.assertNotContains(response, self.empresa_inativa.nome_fantasia)
        self.assert_sem_segredos(response)
        response = self.client.get(self.url('configurar', self.empresa_nova))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.snapshot(), antes)
        self.assertFalse(ConexaoWhatsApp.objects.filter(empresa=self.empresa_nova).exists())
        self.http.assert_not_called()

    def test_mutacoes_exigem_post_e_csrf(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.gerente)
        antes = self.snapshot()
        for nome in ('conectar', 'desconectar'):
            with self.subTest(rota=nome):
                self.assertEqual(self.client.get(self.url(nome)).status_code, 405)
                self.assertEqual(protegido.post(self.url(nome)).status_code, 403)
                self.assertEqual(self.client.delete(self.url(nome)).status_code, 405)
        for nome in ('index', 'configurar', 'status'):
            with self.subTest(rota=nome):
                self.assertEqual(self.client.post(self.url(nome)).status_code, 405)
        self.assertEqual(self.snapshot(), antes)
        self.http.assert_not_called()

    def test_instancias_tem_namespace_aleatorio_persistente_e_empresa_unica(self):
        self.assertNotEqual(self.conexao.identificador, self.outra_conexao.identificador)
        self.assertNotEqual(self.conexao.nome_instancia, self.outra_conexao.nome_instancia)
        self.assertRegex(self.conexao.nome_instancia, r'^mediata-[0-9a-f]{32}$')
        self.assertNotEqual(self.conexao.webhook_secret, self.outra_conexao.webhook_secret)
        nome = self.conexao.nome_instancia
        self.conexao.refresh_from_db()
        self.assertEqual(self.conexao.nome_instancia, nome)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConexaoWhatsApp.objects.create(empresa=self.empresa)
        self.assertEqual(ConexaoWhatsApp.objects.count(), 2)
        self.http.assert_not_called()


class WhatsAppWorkflowTests(WhatsAppFixtures):
    qr_code = (
        'data:image/png;base64,'
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+sHioAAAAASUVORK5CYII='
    )

    def setUp(self):
        super().setUp()
        fabrica = patch('whatsapp.services.EvolutionClient')
        self.provider_factory = fabrica.start()
        self.addCleanup(fabrica.stop)
        self.provider = self.provider_factory.return_value
        self.provider.criar_instancia.return_value = {
            'instance': {'instanceName': self.conexao.nome_instancia, 'status': 'close'},
        }
        self.provider.estado_instancia.return_value = {
            'instance': {'instanceName': self.conexao.nome_instancia, 'state': 'close'},
        }
        self.provider.conectar_instancia.return_value = {
            'base64': self.qr_code, 'code': 'CODIGO-PRIVADO-DO-PROVIDER',
            'count': 1, 'pairingCode': 'PAREAMENTO-PRIVADO-DO-PROVIDER',
            'apikey': settings.EVOLUTION_API_KEY,
        }
        self.provider.desconectar_instancia.return_value = {'status': 'SUCCESS', 'error': False}

    def assert_json_seguro(self, response, *, qr=False):
        dados = response.json()
        self.assertEqual(set(dados), {
            'ok', 'empresa_id', 'estado', 'mensagem', *({'qr_code'} if qr else set()),
        })
        self.assert_sem_segredos(response)
        for detalhe in ('CODIGO-PRIVADO-DO-PROVIDER', 'PAREAMENTO-PRIVADO-DO-PROVIDER'):
            self.assertNotIn(detalhe, response.content.decode())
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('Cookie', response['Vary'])
        return dados

    def test_conectar_usa_empresa_da_url_e_nao_aceita_instancia_ou_segredos_do_post(self):
        outra_antes = ConexaoWhatsApp.objects.filter(pk=self.outra_conexao.pk).values().get()
        response = self.client.post(self.url('conectar'), {
            'empresa': self.outra_empresa.pk, 'empresa_id': self.outra_empresa.pk,
            'instanceName': self.outra_conexao.nome_instancia,
            'webhook_secret': self.outra_conexao.webhook_secret,
            'apikey': 'CHAVE-FORJADA',
        })
        self.assertEqual(response.status_code, 200)
        dados = self.assert_json_seguro(response, qr=True)
        self.assertTrue(dados['ok'])
        self.assertEqual(dados['empresa_id'], self.empresa.pk)
        self.assertEqual(dados['qr_code'], self.qr_code)
        self.assertEqual(dados['estado'], ConexaoWhatsApp.Estado.AGUARDANDO_QR)
        self.conexao.refresh_from_db()
        self.assertTrue(self.conexao.instancia_criada)
        self.assertEqual(self.conexao.estado, ConexaoWhatsApp.Estado.AGUARDANDO_QR)
        self.assertIsNone(self.conexao.operacao_id)
        self.assertIsNone(self.conexao.operacao_iniciada_em)
        nome, webhook = self.provider.criar_instancia.call_args.args
        self.assertEqual(nome, self.conexao.nome_instancia)
        self.assertEqual(webhook['events'], ['CONNECTION_UPDATE'])
        self.assertEqual(webhook['headers'], {
            'X-Mediata-Webhook-Secret': self.conexao.webhook_secret,
        })
        self.assertEqual(webhook['url'], settings.EVOLUTION_WEBHOOK_BASE_URL + reverse(
            'whatsapp:webhook', kwargs={'identificador': self.conexao.identificador},
        ))
        self.provider.conectar_instancia.assert_called_once_with(self.conexao.nome_instancia)
        self.provider.configurar_webhook.assert_called_once_with(self.conexao.nome_instancia, webhook)
        self.assertEqual(ConexaoWhatsApp.objects.filter(pk=self.outra_conexao.pk).values().get(), outra_antes)
        self.assertEqual(ConexaoWhatsApp.objects.count(), 2)
        self.http.assert_not_called()

    @override_settings(EVOLUTION_WEBHOOK_BASE_URL='')
    def test_callback_ausente_desativa_tela_e_impede_criar_instancia_remota(self):
        pagina = self.client.get(self.url('configurar'))
        self.assertEqual(pagina.status_code, 200)
        self.assertFalse(pagina.context['evolution_disponivel'])
        response = self.client.post(self.url('conectar'))
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.assert_json_seguro(response)['ok'])
        self.assertEqual(self.provider.mock_calls, [])
        self.http.assert_not_called()
        self.conexao.refresh_from_db()
        self.assertFalse(self.conexao.instancia_criada)
        self.assertIsNone(self.conexao.operacao_id)

    def test_duas_empresas_conectam_instancias_diferentes_sem_compartilhar_segredo(self):
        primeira = self.client.post(self.url('conectar'))
        self.assertEqual(primeira.status_code, 200)
        self.client.force_login(self.outro_gerente)
        segunda = self.client.post(self.url('conectar', self.outra_empresa))
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(primeira.json()['empresa_id'], self.empresa.pk)
        self.assertEqual(segunda.json()['empresa_id'], self.outra_empresa.pk)
        chamadas = self.provider.criar_instancia.call_args_list
        self.assertEqual([item.args[0] for item in chamadas], [
            self.conexao.nome_instancia, self.outra_conexao.nome_instancia,
        ])
        self.assertNotEqual(chamadas[0].args[1]['headers'], chamadas[1].args[1]['headers'])
        self.assertEqual(ConexaoWhatsApp.objects.count(), 2)
        self.assert_json_seguro(primeira, qr=True)
        self.assert_json_seguro(segunda, qr=True)
        self.http.assert_not_called()

    def test_superusuario_cria_conexao_na_empresa_escolhida_e_reconectar_reutiliza_instancia(self):
        self.client.force_login(self.admin)
        antes = self.snapshot()
        response = self.client.post(self.url('conectar', self.empresa_nova), {'empresa': self.empresa.pk})
        self.assertEqual(response.status_code, 200)
        conexao = ConexaoWhatsApp.objects.get(empresa=self.empresa_nova)
        self.assertEqual(response.json()['empresa_id'], self.empresa_nova.pk)
        self.assertNotIn(conexao.nome_instancia, (self.conexao.nome_instancia, self.outra_conexao.nome_instancia))
        self.provider.estado_instancia.return_value = {
            'instance': {'instanceName': conexao.nome_instancia, 'state': 'connecting'},
        }
        response = self.client.post(self.url('conectar', self.empresa_nova))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ConexaoWhatsApp.objects.filter(empresa=self.empresa_nova).count(), 1)
        self.assertEqual(ConexaoWhatsApp.objects.count(), 3)
        self.provider.criar_instancia.assert_called_once()
        self.assertEqual(self.provider.conectar_instancia.call_count, 2)
        self.assertEqual(list(ConexaoWhatsApp.objects.filter(pk__in=(
            self.conexao.pk, self.outra_conexao.pk,
        )).order_by('pk').values()), antes)
        self.http.assert_not_called()

    def test_status_normaliza_estado_sem_expor_json_bruto_ou_alterar_outra_empresa(self):
        ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).update(instancia_criada=True)
        outra_antes = ConexaoWhatsApp.objects.filter(pk=self.outra_conexao.pk).values().get()
        self.provider.estado_instancia.return_value = {
            'instance': {'instanceName': self.conexao.nome_instancia, 'state': 'open'},
            'apikey': settings.EVOLUTION_API_KEY, 'url': settings.EVOLUTION_API_URL,
        }
        response = self.client.get(self.url('status'))
        self.assertEqual(response.status_code, 200)
        dados = self.assert_json_seguro(response)
        self.assertEqual(dados['estado'], ConexaoWhatsApp.Estado.CONECTADO)
        self.conexao.refresh_from_db()
        self.assertEqual(self.conexao.estado, ConexaoWhatsApp.Estado.CONECTADO)
        self.provider.estado_instancia.assert_called_once_with(self.conexao.nome_instancia)
        self.assertEqual(ConexaoWhatsApp.objects.filter(pk=self.outra_conexao.pk).values().get(), outra_antes)
        self.http.assert_not_called()

    def test_desconectar_preserva_identidade_e_nao_desconecta_instancia_da_outra_empresa(self):
        ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).update(
            instancia_criada=True, estado=ConexaoWhatsApp.Estado.CONECTADO,
        )
        self.provider.estado_instancia.return_value = {'instance': {'state': 'open'}}
        outra_antes = ConexaoWhatsApp.objects.filter(pk=self.outra_conexao.pk).values().get()
        nome, segredo = self.conexao.nome_instancia, self.conexao.webhook_secret
        response = self.client.post(self.url('desconectar'), {'instanceName': self.outra_conexao.nome_instancia})
        self.assertEqual(response.status_code, 200)
        dados = self.assert_json_seguro(response)
        self.assertEqual(dados['estado'], ConexaoWhatsApp.Estado.DESCONECTADO)
        self.provider.desconectar_instancia.assert_called_once_with(nome)
        self.conexao.refresh_from_db()
        self.assertEqual(self.conexao.nome_instancia, nome)
        self.assertEqual(self.conexao.webhook_secret, segredo)
        self.assertEqual(self.conexao.estado, ConexaoWhatsApp.Estado.DESCONECTADO)
        self.assertIsNone(self.conexao.operacao_id)
        self.assertEqual(ConexaoWhatsApp.objects.filter(pk=self.outra_conexao.pk).values().get(), outra_antes)
        self.assertEqual(ConexaoWhatsApp.objects.count(), 2)
        self.http.assert_not_called()

    def test_erro_do_provider_ou_configuracao_indisponivel_libera_operacao_sem_vazar_detalhes(self):
        for erro, esperado in ((EvolutionError('timeout'), 502), (EvolutionError('unavailable'), 503)):
            with self.subTest(codigo=erro.code):
                self.provider.criar_instancia.side_effect = erro
                response = self.client.post(self.url('conectar'))
                self.assertEqual(response.status_code, esperado)
                dados = self.assert_json_seguro(response)
                self.assertFalse(dados['ok'])
                self.conexao.refresh_from_db()
                self.assertFalse(self.conexao.instancia_criada)
                self.assertIsNone(self.conexao.operacao_id)
                self.assertIsNone(self.conexao.operacao_iniciada_em)
        self.http.assert_not_called()

    def test_uma_operacao_em_andamento_bloqueia_disputa_e_lease_expirado_permite_recuperacao(self):
        ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).update(
            operacao_id=uuid4(), operacao_iniciada_em=timezone.now(),
        )
        antes = self.snapshot()
        response = self.client.post(self.url('conectar'))
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.assert_json_seguro(response)['ok'])
        self.assertEqual(self.snapshot(), antes)
        self.provider.criar_instancia.assert_not_called()
        self.provider.conectar_instancia.assert_not_called()
        ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).update(
            operacao_iniciada_em=timezone.now() - timedelta(minutes=6),
        )
        response = self.client.post(self.url('conectar'))
        self.assertEqual(response.status_code, 200)
        self.conexao.refresh_from_db()
        self.assertIsNone(self.conexao.operacao_id)
        self.provider.criar_instancia.assert_called_once()
        self.http.assert_not_called()

    def test_qr_invalido_ou_svg_e_rejeitado_sem_enviar_conteudo_ativo_ao_navegador(self):
        for qr in (
            'data:image/svg+xml,<svg onload="alert(1)"></svg>',
            'data:image/png;base64,conteúdo inválido',
            'javascript:alert(1)',
        ):
            with self.subTest(qr=qr):
                self.provider.conectar_instancia.return_value = {'base64': qr}
                response = self.client.post(self.url('conectar'))
                self.assertEqual(response.status_code, 502)
                dados = self.assert_json_seguro(response)
                self.assertFalse(dados['ok'])
                self.assertNotIn(qr, response.content.decode())
                self.conexao.refresh_from_db()
                self.assertIsNone(self.conexao.operacao_id)
        self.http.assert_not_called()

    def test_callback_de_conexao_durante_preparo_nao_e_sobrescrito_por_qr_atrasado(self):
        publico = Client(enforce_csrf_checks=True)

        def conectar(nome):
            response = publico.post(reverse('whatsapp:webhook', kwargs={
                'identificador': self.conexao.identificador,
            }), {
                'event': 'connection.update', 'instance': nome, 'data': {'state': 'open'},
            }, content_type='application/json', HTTP_X_MEDIATA_WEBHOOK_SECRET=self.conexao.webhook_secret)
            self.assertEqual(response.status_code, 200)
            return {'base64': self.qr_code}

        self.provider.conectar_instancia.side_effect = conectar
        response = self.client.post(self.url('conectar'))
        self.assertEqual(response.status_code, 200)
        dados = self.assert_json_seguro(response)
        self.assertEqual(dados['estado'], ConexaoWhatsApp.Estado.CONECTADO)
        self.assertNotIn('qr_code', dados)
        self.conexao.refresh_from_db()
        self.assertEqual(self.conexao.estado, ConexaoWhatsApp.Estado.CONECTADO)
        self.http.assert_not_called()

    def test_status_antigo_nao_sobrescreve_callback_recebido_durante_consulta_http(self):
        ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).update(
            instancia_criada=True, estado=ConexaoWhatsApp.Estado.DESCONECTADO,
        )
        publico = Client(enforce_csrf_checks=True)

        def estado_antigo(nome):
            response = publico.post(reverse('whatsapp:webhook', kwargs={
                'identificador': self.conexao.identificador,
            }), {
                'event': 'connection.update', 'instance': nome, 'data': {'state': 'open'},
            }, content_type='application/json', HTTP_X_MEDIATA_WEBHOOK_SECRET=self.conexao.webhook_secret)
            self.assertEqual(response.status_code, 200)
            return {'instance': {'instanceName': nome, 'state': 'close'}}

        self.provider.estado_instancia.side_effect = estado_antigo
        response = self.client.get(self.url('status'))
        self.assertEqual(response.status_code, 200)
        dados = self.assert_json_seguro(response)
        self.assertEqual(dados['estado'], ConexaoWhatsApp.Estado.CONECTADO)
        self.conexao.refresh_from_db()
        self.assertEqual(self.conexao.estado, ConexaoWhatsApp.Estado.CONECTADO)
        self.assertIsNotNone(self.conexao.ultimo_evento_em)
        self.http.assert_not_called()

    def test_status_antigo_nao_reabre_conexao_que_foi_desconectada_durante_consulta(self):
        ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).update(
            instancia_criada=True, estado=ConexaoWhatsApp.Estado.CONECTADO,
        )

        def estado_antigo(nome):
            # A ação concorrente consulta um estado atual e termina antes da
            # resposta antiga da consulta original chegar ao servidor.
            self.provider.estado_instancia.side_effect = None
            self.provider.estado_instancia.return_value = {
                'instance': {'instanceName': nome, 'state': 'open'},
            }
            encerramento = self.client.post(self.url('desconectar'))
            self.assertEqual(encerramento.status_code, 200)
            self.assertEqual(encerramento.json()['estado'], ConexaoWhatsApp.Estado.DESCONECTADO)
            return {'instance': {'instanceName': nome, 'state': 'open'}}

        self.provider.estado_instancia.side_effect = estado_antigo
        response = self.client.get(self.url('status'))
        self.assertEqual(response.status_code, 200)
        dados = self.assert_json_seguro(response)
        self.assertEqual(dados['estado'], ConexaoWhatsApp.Estado.DESCONECTADO)
        self.conexao.refresh_from_db()
        self.assertEqual(self.conexao.estado, ConexaoWhatsApp.Estado.DESCONECTADO)
        self.assertIsNone(self.conexao.operacao_id)
        self.provider.desconectar_instancia.assert_called_once_with(self.conexao.nome_instancia)
        self.http.assert_not_called()

    def test_post_valido_com_csrf_conecta_sem_expor_os_segredos_do_servidor(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.gerente)
        response = protegido.get(self.url('configurar'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', protegido.cookies)
        response = protegido.post(self.url('conectar'), {
            'csrfmiddlewaretoken': protegido.cookies['csrftoken'].value,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.assert_json_seguro(response, qr=True)['ok'])
        self.http.assert_not_called()


class WhatsAppWebhookTests(WhatsAppFixtures):
    """O webhook recebe apenas estado de conexão e usa segredo da instância."""

    def webhook_url(self, conexao=None):
        return reverse('whatsapp:webhook', kwargs={
            'identificador': (conexao or self.conexao).identificador,
        })

    def payload(self, **alteracoes):
        dados = {
            'event': 'connection.update', 'instance': self.conexao.nome_instancia,
            'data': {'state': 'open'},
        }
        dados.update(alteracoes)
        return dados

    def enviar(self, dados=None, segredo=None, client=None):
        return (client or self.client).post(
            self.webhook_url(), dados or self.payload(), content_type='application/json',
            HTTP_X_MEDIATA_WEBHOOK_SECRET=segredo or self.conexao.webhook_secret,
        )

    def test_webhook_publico_autenticado_por_segredo_atualiza_so_sua_empresa(self):
        publico = Client(enforce_csrf_checks=True)
        outra_antes = ConexaoWhatsApp.objects.filter(pk=self.outra_conexao.pk).values().get()
        response = self.enviar(client=publico)
        self.assertEqual(response.status_code, 200)
        self.conexao.refresh_from_db()
        self.assertEqual(self.conexao.estado, ConexaoWhatsApp.Estado.CONECTADO)
        self.assertIsNotNone(self.conexao.ultimo_evento_em)
        self.assertEqual(ConexaoWhatsApp.objects.filter(pk=self.outra_conexao.pk).values().get(), outra_antes)
        self.assert_sem_segredos(response)
        self.http.assert_not_called()

    def test_webhook_aceita_evento_maiusculo_e_desconexao_sem_payload_extra(self):
        publico = Client(enforce_csrf_checks=True)
        ConexaoWhatsApp.objects.filter(pk=self.conexao.pk).update(
            estado=ConexaoWhatsApp.Estado.CONECTADO,
        )
        response = self.enviar(self.payload(
            event='CONNECTION_UPDATE',
            data={'state': 'close', 'apikey': settings.EVOLUTION_API_KEY,
                  'message': 'PAYLOAD-PRIVADO-DO-PROVIDER'},
        ), client=publico)
        self.assertEqual(response.status_code, 200)
        self.conexao.refresh_from_db()
        self.assertEqual(self.conexao.estado, ConexaoWhatsApp.Estado.DESCONECTADO)
        self.assertIsNotNone(self.conexao.ultimo_evento_em)
        self.assertNotIn('PAYLOAD-PRIVADO-DO-PROVIDER', response.content.decode())
        self.assert_sem_segredos(response)
        self.http.assert_not_called()

    def test_webhook_nega_segredo_ausente_incorreto_ou_de_outra_empresa(self):
        publico = Client(enforce_csrf_checks=True)
        antes = self.snapshot()
        for segredo in ('incorreto', self.outra_conexao.webhook_secret):
            with self.subTest(segredo=segredo):
                response = self.enviar(segredo=segredo, client=publico)
                self.assertEqual(response.status_code, 403)
                self.assert_sem_segredos(response)
        response = publico.post(self.webhook_url(), self.payload(), content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.snapshot(), antes)
        self.http.assert_not_called()

    def test_webhook_valida_instancia_mesmo_quando_segredo_esta_correto(self):
        publico = Client(enforce_csrf_checks=True)
        antes = self.snapshot()
        response = self.enviar(self.payload(instance=self.outra_conexao.nome_instancia), client=publico)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.snapshot(), antes)
        self.assert_sem_segredos(response)
        response = publico.post(
            reverse('whatsapp:webhook', kwargs={'identificador': uuid4()}),
            self.payload(), content_type='application/json',
            HTTP_X_MEDIATA_WEBHOOK_SECRET=self.conexao.webhook_secret,
        )
        self.assertEqual(response.status_code, 403)
        self.http.assert_not_called()

    def test_webhook_ignora_mensagens_sem_persistir_ou_repassar_payload(self):
        publico = Client(enforce_csrf_checks=True)
        antes = self.snapshot()
        response = self.enviar(self.payload(
            event='messages.upsert',
            data={'messages': [{'message': {'conversation': 'MENSAGEM-PRIVADA-DE-TESTE'}}]},
        ), client=publico)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('MENSAGEM-PRIVADA-DE-TESTE', response.content.decode())
        self.assertEqual(self.snapshot(), antes)
        self.http.assert_not_called()

    def test_webhook_rejeita_json_invalido_e_metodos_inesperados(self):
        publico = Client(enforce_csrf_checks=True)
        antes = self.snapshot()
        response = publico.post(
            self.webhook_url(), '{json inválido', content_type='application/json',
            HTTP_X_MEDIATA_WEBHOOK_SECRET=self.conexao.webhook_secret,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(publico.get(self.webhook_url()).status_code, 405)
        self.assertEqual(self.snapshot(), antes)
        self.http.assert_not_called()
