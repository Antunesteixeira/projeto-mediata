from django.core.exceptions import PermissionDenied
from django.utils.deprecation import MiddlewareMixin

from .access import is_assinante


class AssinanteAccessMiddleware(MiddlewareMixin):
    read_methods = frozenset({'GET', 'HEAD'})
    allowed_views = {
        'index': read_methods,
        'dashboard': read_methods,
        'index-tickets': read_methods,
        'buscar_tickets': read_methods,
        'exibir-ticket': read_methods,
        'perfil-usuario': read_methods,
        'health': read_methods,
        'cadastro-ticket': read_methods | {'POST'},
        'editar-ticket': read_methods | {'POST'},
        'login': read_methods | {'POST'},
        'logout': frozenset({'POST'}),
        'password_change': read_methods | {'POST'},
        'password_change_done': read_methods,
    }

    def process_view(self, request, view_func, view_args, view_kwargs):
        request.is_assinante = is_assinante(request.user)
        if not request.is_assinante:
            return None

        view_name = request.resolver_match.view_name
        if request.method not in self.allowed_views.get(view_name, ()):
            raise PermissionDenied('Seu acesso permite cadastrar e acompanhar seus tickets.')
        if view_name == 'perfil-usuario' and view_kwargs['id'] != request.user.pk:
            raise PermissionDenied('Você pode consultar apenas seu próprio perfil.')
        return None


class EmpresaAccessMiddleware(MiddlewareMixin):
    account_views = {
        'index', 'login', 'logout', 'health', 'password_change', 'password_change_done',
    }
    basic_ticket_views = {
        'dashboard', 'index-tickets', 'buscar_tickets', 'exibir-ticket',
        'tickets-disponiveis', 'ticket-disponivel',
    }
    user_management_views = {'index-usuarios', 'registrar-usuarios', 'editar-usuario', 'editar-usuarios'}

    def process_view(self, request, view_func, view_args, view_kwargs):
        from core.tenancy import empresa_do_usuario, pode_gerenciar_empresa, pode_operar_tickets

        user = request.user
        if not user.is_authenticated or user.is_superuser:
            return None
        view_name = request.resolver_match.view_name
        if view_name.startswith('admin:'):
            raise PermissionDenied('O painel administrativo é exclusivo da administração da plataforma.')
        if is_assinante(user):
            return None
        target_id = view_kwargs.get('user_id', view_kwargs.get('id'))
        own_profile = view_name in {'perfil-usuario', 'editar-usuario', 'editar-usuarios'} and target_id == user.pk
        if view_name in self.account_views or own_profile:
            return None
        if empresa_do_usuario(user) is None:
            raise PermissionDenied('Sua conta precisa estar vinculada a uma empresa ativa.')
        if view_name in self.user_management_views and not pode_gerenciar_empresa(user):
            raise PermissionDenied('A gestão de usuários é restrita aos gerentes da empresa.')
        if not pode_operar_tickets(user) and view_name not in self.basic_ticket_views:
            raise PermissionDenied('Seu acesso permite acompanhar os tickets da sua empresa.')
        return None
