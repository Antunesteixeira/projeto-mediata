"""Consultas automáticas de estado não contam como atividade do usuário."""

from django.urls import Resolver404, resolve
from django_auto_logout.middleware import auto_logout as vendor_auto_logout


LAST_REQUEST_KEY = 'django_auto_logout_last_request'


def _status_automatico(request):
    if request.method != 'GET' or request.headers.get('X-Mediata-Poll') != '1':
        return False
    try:
        match = resolve(request.path_info, urlconf=getattr(request, 'urlconf', None))
    except Resolver404:
        return False
    return match.view_name == 'whatsapp:status'


def auto_logout(get_response):
    verificar_sessao = vendor_auto_logout(get_response)

    def middleware(request):
        automatico = request.user.is_authenticated and _status_automatico(request)
        anterior = request.session.get(LAST_REQUEST_KEY) if automatico else None
        # O pacote sempre verifica o vencimento antes de executar a view.
        response = verificar_sessao(request)
        if automatico and anterior is not None and request.user.is_authenticated:
            request.session[LAST_REQUEST_KEY] = anterior
        return response

    return middleware
