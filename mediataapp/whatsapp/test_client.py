"""O transporte Evolution v2 é simulado; nenhuma mensagem é enviada."""

from unittest.mock import patch

import requests
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from .client import EvolutionClient, EvolutionError


@override_settings(
    EVOLUTION_ENABLED=True,
    EVOLUTION_API_URL='https://evolution.example.invalid/private-root/',
    EVOLUTION_API_KEY='chave-ficticia-do-cliente-http',
    EVOLUTION_API_TIMEOUT=7,
)
class EvolutionClientTests(SimpleTestCase):
    nome = 'mediata-' + 'c' * 32

    def setUp(self):
        transporte = patch('whatsapp.client.requests.request')
        self.http = transporte.start()
        self.addCleanup(transporte.stop)
        self.http.return_value.status_code = 200
        self.http.return_value.json.return_value = {'instance': {'state': 'close'}}

    def assert_erro_seguro(self, erro, *, codigo=None):
        if codigo is not None:
            self.assertEqual(erro.code, codigo)
        mensagem = str(erro)
        self.assertNotIn(settings.EVOLUTION_API_KEY, mensagem)
        self.assertNotIn(settings.EVOLUTION_API_URL.rstrip('/'), mensagem)
        self.assertNotIn(self.nome, mensagem)
        self.assertNotIn('CONTEUDO-PRIVADO-DO-PROVIDER', mensagem)

    def test_rotas_de_configuracao_usam_autenticacao_timeout_e_nao_seguem_redirect(self):
        client = EvolutionClient()
        webhook = {
            'enabled': True, 'url': 'https://mediata.example.invalid/whatsapp/webhook/ficticio/',
            'events': ['CONNECTION_UPDATE'],
        }
        for executar, metodo, caminho in (
            (lambda: client.criar_instancia(self.nome, webhook), 'POST', '/instance/create'),
            (lambda: client.configurar_webhook(self.nome, webhook), 'POST', '/webhook/set/' + self.nome),
            (lambda: client.conectar_instancia(self.nome), 'GET', '/instance/connect/' + self.nome),
            (lambda: client.estado_instancia(self.nome), 'GET', '/instance/connectionState/' + self.nome),
            (lambda: client.desconectar_instancia(self.nome), 'DELETE', '/instance/logout/' + self.nome),
        ):
            with self.subTest(metodo=metodo, caminho=caminho):
                self.http.reset_mock()
                executar()
                args, kwargs = self.http.call_args
                self.assertEqual(args, (metodo, settings.EVOLUTION_API_URL.rstrip('/') + caminho))
                self.assertEqual(kwargs['headers']['apikey'], settings.EVOLUTION_API_KEY)
                self.assertEqual(kwargs['headers']['Accept'], 'application/json')
                self.assertEqual(kwargs['timeout'], (3.05, 7.0))
                self.assertIs(kwargs['allow_redirects'], False)
                self.http.assert_called_once()

    def test_criar_instancia_nao_habilita_leitura_de_mensagens_ou_sincronizacao_de_historico(self):
        webhook = {'enabled': True, 'events': ['CONNECTION_UPDATE']}
        EvolutionClient().criar_instancia(self.nome, webhook)
        dados = self.http.call_args.kwargs['json']
        self.assertEqual(dados['instanceName'], self.nome)
        self.assertEqual(dados['integration'], 'WHATSAPP-BAILEYS')
        for opcao in ('readMessages', 'readStatus', 'syncFullHistory'):
            self.assertIs(dados[opcao], False)
        self.assertEqual(dados['webhook']['events'], ['CONNECTION_UPDATE'])
        self.assertNotIn('message', dados)
        self.assertNotIn('text', dados)

    def test_timeout_e_falha_de_rede_nao_repassam_url_chave_ou_texto_da_excecao(self):
        detalhe = (
            settings.EVOLUTION_API_URL + settings.EVOLUTION_API_KEY
            + self.nome + 'CONTEUDO-PRIVADO-DO-PROVIDER'
        )
        for excecao, codigo in (
            (requests.exceptions.Timeout(detalhe), 'timeout'),
            (requests.exceptions.ConnectionError(detalhe), 'provider_error'),
        ):
            with self.subTest(excecao=type(excecao).__name__):
                self.http.side_effect = excecao
                with self.assertRaises(EvolutionError) as recebido:
                    EvolutionClient().estado_instancia(self.nome)
                self.assert_erro_seguro(recebido.exception, codigo=codigo)
                self.assertEqual(recebido.exception.status_code, 502)

    def test_status_http_de_erro_e_redirect_nao_expoem_payload_do_provider(self):
        self.http.return_value.json.return_value = {
            'apikey': settings.EVOLUTION_API_KEY, 'instanceName': self.nome,
            'message': 'CONTEUDO-PRIVADO-DO-PROVIDER',
        }
        for status in (301, 302, 400, 401, 403, 404, 409, 500, 503):
            with self.subTest(status=status):
                self.http.return_value.status_code = status
                with self.assertRaises(EvolutionError) as recebido:
                    EvolutionClient().estado_instancia(self.nome)
                self.assertEqual(recebido.exception.provider_status, status)
                self.assert_erro_seguro(recebido.exception, codigo='provider_error')

    def test_json_malformado_estrutura_invalida_e_error_true_sao_rejeitados(self):
        for dados in (None, [], 'CONTEUDO-PRIVADO-DO-PROVIDER', {'error': True}):
            with self.subTest(dados=dados):
                self.http.return_value.json.return_value = dados
                with self.assertRaises(EvolutionError) as recebido:
                    EvolutionClient().conectar_instancia(self.nome)
                self.assert_erro_seguro(recebido.exception, codigo='invalid_response')
        self.http.return_value.json.side_effect = ValueError('CONTEUDO-PRIVADO-DO-PROVIDER')
        with self.assertRaises(EvolutionError) as recebido:
            EvolutionClient().estado_instancia(self.nome)
        self.assert_erro_seguro(recebido.exception, codigo='invalid_response')

    def test_configuracao_ausente_ou_url_invalida_impede_chamada_http(self):
        for alteracoes in (
            {'EVOLUTION_ENABLED': False}, {'EVOLUTION_API_KEY': ''}, {'EVOLUTION_API_URL': ''},
            {'EVOLUTION_API_URL': 'file:///etc/passwd'},
            {'EVOLUTION_API_URL': 'https://usuario:senha@example.invalid'},
            {'EVOLUTION_API_URL': 'https://example.invalid?apikey=secreto'},
            {'EVOLUTION_API_URL': 'https://example.invalid#fragmento'},
        ):
            with self.subTest(alteracoes=alteracoes), override_settings(**alteracoes):
                with self.assertRaises(EvolutionError) as recebido:
                    EvolutionClient()
                self.assertEqual(recebido.exception.code, 'unavailable')
                self.assertEqual(recebido.exception.status_code, 503)
        self.http.assert_not_called()

    def test_timeout_tem_limites_finitos_e_aceita_conexao_e_leitura_separados(self):
        for timeout in (0, -1, 61, 'inválido', float('inf'), float('nan'), (1,), (1, 61)):
            with self.subTest(timeout=timeout), override_settings(EVOLUTION_API_TIMEOUT=timeout):
                with self.assertRaises(EvolutionError):
                    EvolutionClient()
        self.http.assert_not_called()
        with override_settings(EVOLUTION_API_TIMEOUT=(2, 11)):
            EvolutionClient().estado_instancia(self.nome)
        self.assertEqual(self.http.call_args.kwargs['timeout'], (2.0, 11.0))

    def test_nome_de_instancia_na_url_e_codificado_em_vez_de_alterar_o_caminho(self):
        EvolutionClient().estado_instancia('instancia/../outra?segredo=teste')
        url = self.http.call_args.args[1]
        self.assertTrue(url.endswith('/instancia%2F..%2Foutra%3Fsegredo%3Dteste'))
        self.assertNotIn('?segredo=', url)

    def test_enviar_texto_usa_numero_e_mensagem_recebidos_com_timeout_e_instancia_correta(self):
        numero = '5511999990001'
        texto = 'Ticket #WATST001\nDescrição: atendimento fictício'
        self.http.return_value.json.return_value = {
            'key': {'id': 'MENSAGEM-FICTICIA-001', 'remoteJid': numero + '@s.whatsapp.net'},
            'status': 'PENDING',
        }
        EvolutionClient().enviar_texto(self.nome, numero, texto)
        args, kwargs = self.http.call_args
        self.assertEqual(args, (
            'POST', settings.EVOLUTION_API_URL.rstrip('/') + '/message/sendText/' + self.nome,
        ))
        self.assertEqual(kwargs['json']['number'], numero)
        self.assertEqual(kwargs['json']['text'], texto)
        self.assertEqual(kwargs['headers']['apikey'], settings.EVOLUTION_API_KEY)
        self.assertEqual(kwargs['timeout'], (3.05, 7.0))
        self.assertFalse(kwargs['allow_redirects'])
        self.http.assert_called_once()

    def test_timeout_ao_enviar_texto_nao_reexecuta_requisicao_automaticamente(self):
        self.http.side_effect = requests.exceptions.Timeout('CONTEUDO-PRIVADO-DO-PROVIDER')
        with self.assertRaises(EvolutionError) as recebido:
            EvolutionClient().enviar_texto(self.nome, '5511999990001', 'Mensagem fictícia')
        self.assert_erro_seguro(recebido.exception, codigo='timeout')
        self.http.assert_called_once()
