from core.tenancy import empresa_do_usuario, pode_gerenciar_empresa, pode_operar_tickets
from rolepermissions.checkers import has_permission
from .access import is_assinante


def access_permissions(request):
    restricted = request.is_assinante if hasattr(request, 'is_assinante') else is_assinante(request.user)
    company = empresa_do_usuario(request.user)
    can_manage = pode_gerenciar_empresa(request.user)
    return {
        'is_assinante': restricted,
        'empresa_atual': company,
        'empresa_vinculada': company.nome_fantasia if company is not None else '',
        'pode_operar_tickets': pode_operar_tickets(request.user),
        'pode_gerenciar_usuarios': can_manage,
        'pode_gerenciar_empresa': can_manage,
        'pode_acessar_financeiro': can_manage,
        'pode_criar_ticket': bool(
            request.user.is_authenticated and (
                restricted or request.user.is_superuser
                or (pode_operar_tickets(request.user) and has_permission(request.user, 'criar_ticket'))
            )
        ),
    }
