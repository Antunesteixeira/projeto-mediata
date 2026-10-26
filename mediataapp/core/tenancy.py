from django.contrib.auth import get_user_model

from usuarios.access import is_assinante


def empresa_do_usuario(user):
    if not user.is_authenticated or is_assinante(user):
        return None
    from usuarios.models import UsuarioEmpresa

    try:
        empresa = user.vinculo_empresa.empresa
    except UsuarioEmpresa.DoesNotExist:
        return None
    return empresa if empresa.ativo else None


def tickets_da_empresa(user):
    from tickets.models import Ticket

    tickets = Ticket.objects.all()
    if not user.is_authenticated or not user.is_active:
        return tickets.none()
    if user.is_superuser:
        return tickets
    if is_assinante(user):
        return tickets.filter(usuario=user)
    empresa = empresa_do_usuario(user)
    if empresa is None:
        return tickets.none()
    tickets = tickets.filter(empresa=empresa)
    if pode_operar_tickets(user) and not pode_gerenciar_empresa(user):
        tickets = tickets.filter(usuario=user)
    return tickets


def dados_da_empresa(user, queryset, campo='empresa'):
    if not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    empresa = empresa_do_usuario(user)
    return queryset.filter(**{campo: empresa}) if empresa is not None else queryset.none()


def usuarios_da_empresa(user):
    users = get_user_model().objects.all()
    if not user.is_authenticated:
        return users.none()
    if user.is_superuser:
        return users
    empresa = empresa_do_usuario(user)
    if empresa is None:
        return users.none()
    return users.filter(vinculo_empresa__empresa=empresa).exclude(
        is_superuser=True,
    ).exclude(groups__name='assinante').distinct()


def pode_assumir_ticket(user):
    return pode_gerenciar_empresa(user)


def pode_consultar_fila(user):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    if is_assinante(user) or empresa_do_usuario(user) is None:
        return False
    return not pode_operar_tickets(user) or pode_gerenciar_empresa(user)


def pode_gerenciar_empresa(user):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return bool(
        not is_assinante(user)
        and empresa_do_usuario(user) is not None
        and user.groups.filter(name='gerente').exists()
    )


def pode_operar_tickets(user):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return bool(
        not is_assinante(user)
        and empresa_do_usuario(user) is not None
        and user.groups.filter(name__in=('gerente', 'operador')).exists()
    )


def pode_acessar_financeiro(user):
    """Valores e documentos financeiros são restritos à gestão da empresa."""
    return pode_gerenciar_empresa(user)
