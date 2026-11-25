"""Cliente Evolution API v2, com operações explícitas e sem tentativas automáticas."""

from urllib.parse import quote, urlsplit

import requests
from django.conf import settings


ERROR_MESSAGES = {
    'unavailable': 'A integração WhatsApp está indisponível. Entre em contato com a administração.',
    'timeout': 'A conexão demorou a responder. Tente novamente em alguns instantes.',
    'provider_error': 'Não foi possível comunicar com o serviço WhatsApp. Tente novamente.',
    'invalid_response': 'Não foi possível confirmar a resposta do serviço WhatsApp. Tente novamente.',
    'busy': 'Já existe uma operação em andamento para esta empresa. Aguarde alguns instantes.',
}


class EvolutionError(Exception):
    def __init__(self, code='provider_error', *, provider_status=None):
        self.code = code if isinstance(code, str) and code in ERROR_MESSAGES else 'provider_error'
        self.provider_status = provider_status
        self.status_code = 503 if self.code == 'unavailable' else 409 if self.code == 'busy' else 502
        self.mensagem = ERROR_MESSAGES[self.code]
        super().__init__(self.mensagem)


def _validar_url_base(value):
    base = str(value or '').rstrip('/')
    try:
        parsed = urlsplit(base)
        valid = (
            parsed.scheme in ('http', 'https') and bool(parsed.hostname)
            and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise EvolutionError('unavailable')
    return base


def url_base_webhook():
    return _validar_url_base(getattr(settings, 'EVOLUTION_WEBHOOK_BASE_URL', ''))


def configuracao_disponivel():
    try:
        EvolutionClient()
        url_base_webhook()
    except EvolutionError:
        return False
    return True


class EvolutionClient:
    def __init__(self):
        self.base_url = _validar_url_base(getattr(settings, 'EVOLUTION_API_URL', ''))
        self.api_key = str(getattr(settings, 'EVOLUTION_API_KEY', '') or '')
        configured_timeout = getattr(settings, 'EVOLUTION_API_TIMEOUT', 10)
        try:
            if isinstance(configured_timeout, (tuple, list)):
                if len(configured_timeout) != 2:
                    raise ValueError
                self.timeout = tuple(float(value) for value in configured_timeout)
            else:
                self.timeout = (3.05, float(configured_timeout))
            if not all(0 < value <= 60 for value in self.timeout):
                raise ValueError
        except (TypeError, ValueError):
            raise EvolutionError('unavailable') from None
        if not getattr(settings, 'EVOLUTION_ENABLED', False) or not self.api_key:
            raise EvolutionError('unavailable')

    def _request(self, method, path, *, payload=None):
        try:
            response = requests.request(
                method, self.base_url + path,
                headers={'apikey': self.api_key, 'Accept': 'application/json'},
                json=payload, timeout=self.timeout, allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise EvolutionError('timeout') from None
        except requests.exceptions.RequestException:
            raise EvolutionError() from None
        if not 200 <= response.status_code < 300:
            raise EvolutionError(provider_status=response.status_code)
        try:
            data = response.json()
        except (TypeError, ValueError, RecursionError):
            raise EvolutionError('invalid_response') from None
        if not isinstance(data, dict) or data.get('error'):
            raise EvolutionError('invalid_response')
        return data

    def criar_instancia(self, nome, webhook):
        return self._request('POST', '/instance/create', payload={
            'instanceName': nome,
            'integration': 'WHATSAPP-BAILEYS',
            'qrcode': False,
            'readMessages': False,
            'readStatus': False,
            'syncFullHistory': False,
            'groupsIgnore': True,
            'webhook': webhook,
        })

    def configurar_webhook(self, nome, webhook):
        return self._request('POST', f'/webhook/set/{quote(nome, safe="")}', payload={'webhook': webhook})

    def conectar_instancia(self, nome):
        return self._request('GET', f'/instance/connect/{quote(nome, safe="")}')

    def estado_instancia(self, nome):
        return self._request('GET', f'/instance/connectionState/{quote(nome, safe="")}')

    def desconectar_instancia(self, nome):
        return self._request('DELETE', f'/instance/logout/{quote(nome, safe="")}')

    def enviar_texto(self, nome, numero, texto):
        return self._request('POST', f'/message/sendText/{quote(nome, safe="")}', payload={
            'number': numero, 'text': texto,
        })
