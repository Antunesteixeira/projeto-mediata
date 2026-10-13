from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from core.tenancy import empresa_do_usuario, pode_operar_tickets, tickets_da_empresa


def exigir_empresa(user):
    if user.is_superuser:
        return None
    empresa = empresa_do_usuario(user)
    if empresa is None:
        raise PermissionDenied('Seu usuário precisa estar vinculado a uma empresa ativa.')
    return empresa


def ticket_de_operacao(request, **lookup):
    if not pode_operar_tickets(request.user):
        raise PermissionDenied('Seu perfil permite apenas acompanhar os tickets.')
    return get_object_or_404(tickets_da_empresa(request.user), **lookup)
