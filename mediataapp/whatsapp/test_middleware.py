"""Polling mantém a verificação de expiração sem renovar a inatividade."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth import SESSION_KEY, logout
from django.contrib.auth.models import User
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import include, path

from .middleware import LAST_REQUEST_KEY, auto_logout


def resposta(request, **kwargs):
    return HttpResponse('autenticado' if request.user.is_authenticated else 'anônimo')


urlpatterns = [
    path('whatsapp/', include(([
        path('status/<int:empresa_id>/', resposta, name='status'),
        path('configurar/<int:empresa_id>/', resposta, name='configurar'),
        path('conectar/<int:empresa_id>/', resposta, name='conectar'),
    ], 'whatsapp'), namespace='whatsapp')),
    path('outro/status/<int:empresa_id>/', resposta, name='status'),
]


@override_settings(
    ROOT_URLCONF=__name__,
    SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies',
    AUTO_LOGOUT={
        'IDLE_TIME': timedelta(minutes=120),
        'MESSAGE': 'A sessão expirou.',
    },
)
class WhatsAppPollingSessionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inicio = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
        self.user = User(pk=1, username='usuario-polling-ficticio', last_login=self.inicio)

    def request(self, *, metodo='get', caminho='/whatsapp/status/1/',
                header='1', sessao=None, anterior=None):
        headers = {'HTTP_X_MEDIATA_POLL': header} if header is not None else {}
        request = getattr(self.factory, metodo)(caminho, **headers)
        SessionMiddleware(resposta).process_request(request)
        if sessao is not None:
            request.session = sessao
        request.user = self.user
        request.session[SESSION_KEY] = str(self.user.pk)
        if anterior is not None:
            request.session[LAST_REQUEST_KEY] = anterior.isoformat()
        MessageMiddleware(resposta).process_request(request)
        return request

    def executar(self, request, agora, view=resposta):
        with patch('django_auto_logout.middleware.now', return_value=agora):
            return auto_logout(view)(request)

    def test_polls_repetidos_nao_renovam_timestamp_e_sessao_expira_apos_120_minutos(self):
        request = self.request(anterior=self.inicio)
        sessao = request.session
        sessao['rascunho'] = 'informação temporária'
        for minutos in (1, 30, 60, 119):
            with self.subTest(minutos=minutos):
                request = self.request(sessao=sessao)
                response = self.executar(request, self.inicio + timedelta(minutes=minutos))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(request.user.is_authenticated)
                self.assertEqual(sessao[LAST_REQUEST_KEY], self.inicio.isoformat())
        request = self.request(sessao=sessao)
        response = self.executar(request, self.inicio + timedelta(minutes=120, seconds=1))
        self.assertFalse(request.user.is_authenticated)
        self.assertEqual(response.content.decode(), 'anônimo')
        self.assertNotIn(LAST_REQUEST_KEY, request.session)
        self.assertNotIn(SESSION_KEY, request.session)
        self.assertNotIn('rascunho', request.session)

    def test_primeiro_poll_inicializa_timestamp_e_polls_seguinte_preservam_inicio(self):
        request = self.request()
        self.executar(request, self.inicio)
        self.assertEqual(request.session[LAST_REQUEST_KEY], self.inicio.isoformat())
        proximo = self.request(sessao=request.session)
        self.executar(proximo, self.inicio + timedelta(minutes=5))
        self.assertEqual(proximo.session[LAST_REQUEST_KEY], self.inicio.isoformat())
        self.assertTrue(proximo.user.is_authenticated)

    def test_consultas_manuais_e_outros_endpoints_renovam_atividade_normalmente(self):
        agora = self.inicio + timedelta(minutes=10)
        for metodo, caminho, header in (
            ('get', '/whatsapp/status/1/', None),
            ('get', '/whatsapp/status/1/', 'true'),
            ('get', '/whatsapp/status/1/', '1 '),
            ('post', '/whatsapp/status/1/', '1'),
            ('post', '/whatsapp/conectar/1/', '1'),
            ('get', '/whatsapp/configurar/1/', '1'),
            ('get', '/outro/status/1/', '1'),
            ('get', '/whatsapp/status/1/extra/', '1'),
            ('get', '/whatsapp/status/1', '1'),
        ):
            with self.subTest(metodo=metodo, caminho=caminho, header=header):
                request = self.request(metodo=metodo, caminho=caminho,
                                       header=header, anterior=self.inicio)
                self.executar(request, agora)
                self.assertTrue(request.user.is_authenticated)
                self.assertEqual(request.session[LAST_REQUEST_KEY], agora.isoformat())

    def test_logout_feito_pela_view_nao_restaura_timestamp_ou_dados_da_sessao(self):
        def sair(request):
            logout(request)
            return HttpResponse(status=204)

        request = self.request(anterior=self.inicio)
        response = self.executar(request, self.inicio + timedelta(minutes=5), view=sair)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(request.user.is_authenticated)
        self.assertNotIn(LAST_REQUEST_KEY, request.session)
        self.assertNotIn(SESSION_KEY, request.session)

    @override_settings(AUTO_LOGOUT={
        'IDLE_TIME': timedelta(minutes=120), 'SESSION_TIME': timedelta(minutes=30),
    })
    def test_poll_tambem_respeita_limite_absoluto_da_sessao_do_pacote(self):
        request = self.request(anterior=self.inicio + timedelta(minutes=25))
        self.executar(request, self.inicio + timedelta(minutes=31))
        self.assertFalse(request.user.is_authenticated)
        self.assertNotIn(LAST_REQUEST_KEY, request.session)
