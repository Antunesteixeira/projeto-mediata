from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import ColaboradorForm
from .models import Colaborador
from django.contrib.auth.decorators import login_required
from usuarios.forms import CustomUserCreationForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from clientes.forms import salvar_form_empresa
from django.views.decorators.http import require_POST
from core.tenancy import (
    dados_da_empresa, empresa_do_usuario, pode_gerenciar_empresa,
)


def _exigir_gestao(user):
    if not pode_gerenciar_empresa(user):
        raise PermissionDenied('Seu acesso não permite gerenciar colaboradores da empresa.')


def _form_usuario_colaborador(request, colaborador, data=None):
    form = CustomUserCreationForm(
        data, actor=request.user,
        initial={'email': colaborador.email or '', 'empresa': colaborador.empresa_id},
    )
    form.fields['group'].queryset = form.fields['group'].queryset.exclude(name='assinante')
    if 'empresa' in form.fields:
        form.fields['empresa'].queryset = form.fields['empresa'].queryset.filter(
            pk=colaborador.empresa_id,
        )
    return form

@login_required
def criar_usuario_para_colaborador(request, colaborador_id):
    if not pode_gerenciar_empresa(request.user):
        raise PermissionDenied('Somente o gerente pode criar usuários para colaboradores.')
    colaboradores = dados_da_empresa(request.user, Colaborador.objects.all())
    colaborador = get_object_or_404(colaboradores, pk=colaborador_id)
    if colaborador.empresa_id is None or not colaborador.empresa.ativo:
        raise PermissionDenied('Vincule o colaborador a uma empresa ativa antes de criar o usuário.')
    if colaborador.user:
        messages.error(request, 'Este colaborador já possui um usuário vinculado.')
        return redirect('perfil_colaborador', id=colaborador.id)

    if request.method == 'POST':
        with transaction.atomic():
            colaborador = get_object_or_404(colaboradores.select_for_update(), pk=colaborador_id)
            if colaborador.user_id:
                messages.error(request, 'Este colaborador já possui um usuário vinculado.')
                return redirect('perfil_colaborador', id=colaborador.id)
            form = _form_usuario_colaborador(request, colaborador, request.POST)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        user = form.save()
                        empresa = empresa_do_usuario(user)
                        if empresa is None or empresa.pk != colaborador.empresa_id:
                            raise ValidationError('O usuário precisa pertencer à mesma empresa do colaborador.')
                        colaborador.user = user
                        colaborador.save(update_fields=['user'])
                except ValidationError as error:
                    form.add_error(None, error)
                except IntegrityError:
                    form.add_error(None, 'Não foi possível vincular o usuário. Verifique se o cadastro já existe.')
                else:
                    messages.success(request, f'Usuário {user.username} criado e vinculado ao colaborador.')
                    return redirect('perfil_colaborador', id=colaborador.id)
    else:
        form = _form_usuario_colaborador(request, colaborador)

    return render(
        request,
        'colaboradores/criar_usuario.html',
        {'form': form, 'colaborador': colaborador},
    )


@login_required
def cadastrar_colaborador(request):
    _exigir_gestao(request.user)
    if request.method == "POST":
        form = ColaboradorForm(request.POST, actor=request.user)
        if form.is_valid():
            if salvar_form_empresa(form) is not None:
                messages.success(request, "Colaborador cadastrado com sucesso!")
                return redirect('lista_colaboradores')
        else:
            messages.error(request, "Erro ao cadastrar colaborador. Verifique os campos.")
    else:
        form = ColaboradorForm(actor=request.user)

    return render(request, 'colaboradores/cadastrar.html', {'form': form})

@login_required
def lista_colaboradores(request):
    _exigir_gestao(request.user)
    colaboradores = dados_da_empresa(request.user, Colaborador.objects.all())
    return render(request, 'colaboradores/listar_colaboradores.html', {'colaboradores': colaboradores})

@login_required
def editar_colaborador(request, colaborador_id):
    _exigir_gestao(request.user)
    colaborador = get_object_or_404(dados_da_empresa(request.user, Colaborador.objects.all()), id=colaborador_id)

    if request.method == 'POST':
        form = ColaboradorForm(request.POST, instance=colaborador, actor=request.user)
        if form.is_valid():
            if salvar_form_empresa(form) is not None:
                messages.success(request, "Colaborador editado com sucesso!")
                return redirect('lista_colaboradores')
    else:
        form = ColaboradorForm(instance=colaborador, actor=request.user)

    return render(request, 'colaboradores/editar-colaborador.html', {'form': form, 'colaborador': colaborador})

@login_required
@require_POST
def deletar_colaborador(request, colaborador_id):
    _exigir_gestao(request.user)
    colaborador = get_object_or_404(dados_da_empresa(request.user, Colaborador.objects.all()), pk=colaborador_id)
    if request.method == "POST":
        nome = str(colaborador)  # ou cliente.nome, conforme seu modelo
        colaborador.delete()
        messages.success(request, f"Colaborador '{nome}' deletado com sucesso.")
        return redirect('lista_colaboradores')  # ajuste para a rota da lista de clientes

# views.py
@login_required
def perfil_colaborador(request, id):
    _exigir_gestao(request.user)
    colaborador = get_object_or_404(dados_da_empresa(request.user, Colaborador.objects.all()), id=id)
    context = {
        'colaborador': colaborador,
    }
    return render(request, 'colaboradores/perfil-colaborador.html', context)
