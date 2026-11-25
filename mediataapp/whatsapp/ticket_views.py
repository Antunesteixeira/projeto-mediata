from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from tickets.access import ticket_de_operacao

from .client import EvolutionError
from .ticket_services import TicketWhatsAppError, enviar_ticket, montar_previa


def _json(data, *, status=200):
    response = JsonResponse(data, status=status)
    patch_vary_headers(response, ('Cookie',))
    return response


@login_required
@never_cache
@require_GET
def previa(request, key):
    ticket = ticket_de_operacao(request, key=key)
    try:
        return _json(montar_previa(ticket, request.user))
    except (TicketWhatsAppError, EvolutionError) as error:
        return _json({'ok': False, 'mensagem': error.mensagem}, status=error.status_code)


@login_required
@never_cache
@require_POST
def enviar(request, key):
    ticket = ticket_de_operacao(request, key=key)
    try:
        data, status = enviar_ticket(ticket, request.user, request.POST.get('confirmacao', ''))
    except (TicketWhatsAppError, EvolutionError) as error:
        return _json({'ok': False, 'mensagem': error.mensagem}, status=error.status_code)
    return _json(data, status=status)
