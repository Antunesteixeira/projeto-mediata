from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from .models import Insumos
from .forms import InsumoForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import login_required

from django.db.models import ProtectedError

from django.http import JsonResponse

from django.db.models import Q

from rolepermissions.decorators import has_role_decorator
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from core.tenancy import dados_da_empresa, pode_gerenciar_empresa
from clientes.forms import salvar_form_empresa


def _exigir_gestao(user):
    if not pode_gerenciar_empresa(user):
        raise PermissionDenied('Seu acesso não permite gerenciar insumos da empresa.')

#@has_role_decorator('gerente')
@login_required
def insumos(request):
    _exigir_gestao(request.user)
    insumos_obj = dados_da_empresa(request.user, Insumos.objects.all())
    if request.method == "POST":
        form = InsumoForm(request.POST, actor=request.user)
        if form.is_valid():
            if salvar_form_empresa(form) is not None:
                messages.add_message(request, messages.SUCCESS, "Insumo cadastrado com sucesso!")
                return redirect('index-insumos')
        else:
            messages.add_message(request, messages.ERROR, "Não foi possível cadastrar o insumo, revise os dados!")
        
    else:
        form = InsumoForm(actor=request.user)
    
    context = {
        'form': form,
        'insumos': insumos_obj,
    }
    return render(request, 'insumos/index-insumos.html', context)

#@has_role_decorator('gerente')
@login_required
def editar_insumos(request, id):
    _exigir_gestao(request.user)
    insumos = dados_da_empresa(request.user, Insumos.objects.all())
    insumo = get_object_or_404(insumos, id=id)
    form = InsumoForm(request.POST if request.method == 'POST' else None, instance=insumo, actor=request.user)

    if form.is_valid():
        # Verifica se os dados do formulário foram alterados
        if form.has_changed(): 
            if salvar_form_empresa(form) is not None:
                messages.success(request, f"Insumo {insumo.codigo.upper()} - {insumo.insumo.upper()} atualizado com sucesso!")
                return redirect('index-insumos')

        else:
            messages.info(request, "Nenhuma alteração foi detectada.")
            return redirect('index-insumos')

    context = {
        'form': form,
        'insumo': insumo,
        'insumos': insumos,
    }
    #return HttpResponse(insumo.valor_unit)
    return render(request, 'insumos/index-insumos.html', context)

#@has_role_decorator('gerente')
@login_required
@require_POST
def deletar_insumo(request, id):
    _exigir_gestao(request.user)
    insumo = get_object_or_404(dados_da_empresa(request.user, Insumos.objects.all()), id=id)

    # opcional: checar permissão extra, ex:
    # if not request.user.has_perm('app.delete_ticket'):
    #     messages.error(request, "Você não tem permissão para excluir este ticket.")
    #     return redirect('exibir-ticket', key=key)

    try:
        insumo.delete()
        messages.success(request, f"O Insumo #{insumo.insumo} foi deletado com sucesso!")
    except ProtectedError:
        messages.error(request, "Não foi possível deletar o ticket porque há objetos relacionados protegendo-o.")
    return redirect('index-insumos') 
