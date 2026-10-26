from django.shortcuts import render, get_object_or_404, redirect
from .models import Cliente
from django.contrib.auth.decorators import login_required
from .forms import ClienteForm, salvar_form_empresa
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from core.tenancy import dados_da_empresa, pode_gerenciar_empresa


def _exigir_gestao(user):
    if not pode_gerenciar_empresa(user):
        raise PermissionDenied('Seu acesso não permite gerenciar clientes da empresa.')

@login_required
def cadastrar_cliente(request):
    _exigir_gestao(request.user)
    if request.method == 'POST':
        form = ClienteForm(request.POST, actor=request.user)
        if form.is_valid():
            if salvar_form_empresa(form) is not None:
                messages.success(request, "Cliente cadastrado com sucesso.")
                return redirect('listar-clientes')
    else:
        form = ClienteForm(actor=request.user)

    return render(request, 'clientes/cadastro-cliente.html', {'form': form})

@login_required
def listar_clientes(request):
    _exigir_gestao(request.user)
    clientes = dados_da_empresa(request.user, Cliente.objects.all()).order_by('-data_cadastro')
    return render(request, 'clientes/listar-clientes.html', {'clientes': clientes})

@login_required
def editar_cliente(request, cliente_id):
    _exigir_gestao(request.user)
    cliente = get_object_or_404(dados_da_empresa(request.user, Cliente.objects.all()), id=cliente_id)

    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente, actor=request.user)
        if form.is_valid():
            if salvar_form_empresa(form) is not None:
                messages.success(request, "Cliente editado com sucesso.")
                return redirect('listar-clientes')
    else:
        form = ClienteForm(instance=cliente, actor=request.user)

    return render(request, 'clientes/editar-cliente.html', {'form': form, 'cliente': cliente})

@login_required
@require_POST
def deletar_cliente(request, cliente_id):
    _exigir_gestao(request.user)
    cliente = get_object_or_404(dados_da_empresa(request.user, Cliente.objects.all()), pk=cliente_id)
    if request.method == "POST":
        nome = str(cliente)  # ou cliente.nome, conforme seu modelo
        cliente.delete()
        messages.success(request, f"Cliente '{nome}' deletado com sucesso.")
        return redirect('listar-clientes')  # ajuste para a rota da lista de clientes

# views.py
@login_required
def perfil_cliente(request, id):
    _exigir_gestao(request.user)
    cliente = get_object_or_404(dados_da_empresa(request.user, Cliente.objects.all()), id=id)
    context = {
        'cliente': cliente,
    }
    return render(request, 'clientes/perfil-cliente.html', context)
