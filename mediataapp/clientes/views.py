from django.shortcuts import render, get_object_or_404, redirect
from .models import Cliente
from django.contrib.auth.decorators import login_required
from .forms import ClienteForm
from django.contrib import messages

@login_required
def cadastrar_cliente(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Cliente cadastrado com sucesso.")
            return redirect('listar-clientes')  # Substitua pela sua URL de listagem
    else:
        form = ClienteForm()

    return render(request, 'clientes/cadastro-cliente.html', {'form': form})

@login_required
def listar_clientes(request):
    clientes = Cliente.objects.all().order_by('-data_cadastro')  # Mais recentes primeiro
    return render(request, 'clientes/listar-clientes.html', {'clientes': clientes})

@login_required
def editar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, f"Cliente editado com sucesso.")
            return redirect('listar-clientes')  # Redireciona para a listagem após salvar
    else:
        form = ClienteForm(instance=cliente)

    return render(request, 'clientes/editar-cliente.html', {'form': form, 'cliente': cliente})

@login_required
def deletar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    if request.method == "POST":
        nome = str(cliente)  # ou cliente.nome, conforme seu modelo
        cliente.delete()
        messages.success(request, f"Cliente '{nome}' deletado com sucesso.")
        return redirect('listar-clientes')  # ajuste para a rota da lista de clientes
    # GET -> mostrar página de confirmação
    return render(request, 'clientes/listar_cleintes.html', {'cliente': cliente})