from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from core.tenancy import empresa_do_usuario, pode_gerenciar_empresa, usuarios_da_empresa
from .forms import CustomUserCreationForm, CustomUserEditForm


def _require_manager(user):
    if not pode_gerenciar_empresa(user):
        raise PermissionDenied('A gestão de usuários é restrita aos gerentes da empresa.')


@login_required
def usuarios(request):
    _require_manager(request.user)
    users = usuarios_da_empresa(request.user).select_related('vinculo_empresa__empresa').prefetch_related('groups')
    return render(request, 'usuarios/index-usuarios.html', {
        'usuarios': users,
        'grupos': Group.objects.all().order_by('name'),
    })


@login_required
def cadastro_usuarios(request):
    return register(request)


@login_required
def editar_usuarios(request, id):
    return editar_usuario(request, user_id=id)


@login_required
def register(request):
    _require_manager(request.user)
    form = CustomUserCreationForm(request.POST if request.method == 'POST' else None, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Usuário cadastrado com sucesso!')
        return redirect('index-usuarios')
    return render(request, 'usuarios/cadastro-usuarios.html', {'form': form})


@login_required
def editar_usuario(request, user_id):
    if user_id == request.user.pk:
        target = request.user
    else:
        _require_manager(request.user)
        target = get_object_or_404(usuarios_da_empresa(request.user), pk=user_id)
    form = CustomUserEditForm(
        request.POST if request.method == 'POST' else None,
        instance=target, actor=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Usuário atualizado com sucesso.')
        if pode_gerenciar_empresa(request.user):
            return redirect('index-usuarios')
        return redirect('perfil-usuario', id=request.user.pk)
    return render(request, 'usuarios/editar-usuario.html', {'form': form, 'usuario': target})


@login_required
def perfil_usuario(request, id):
    if id == request.user.pk:
        target = request.user
    else:
        _require_manager(request.user)
        target = get_object_or_404(usuarios_da_empresa(request.user), pk=id)
    return render(request, 'usuarios/perfil-usuario.html', {
        'usuario_perfil': target,
        'empresa_perfil': empresa_do_usuario(target),
        'can_edit_profile': request.user.is_superuser or target.pk == request.user.pk or pode_gerenciar_empresa(request.user),
    })
