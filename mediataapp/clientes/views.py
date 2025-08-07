from django.shortcuts import render, get_object_or_404, redirect
from .models import Cliente

from .forms import ClienteForm

def cadastrar_cliente(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('lista-clientes')  # Substitua pela sua URL de listagem
    else:
        form = ClienteForm()

    return render(request, 'clientes/cadastro-cliente.html', {'form': form})

def listar_clientes(request):
    clientes = Cliente.objects.all().order_by('-data_cadastro')  # Mais recentes primeiro
    return render(request, 'clientes/listar-clientes.html', {'clientes': clientes})

def editar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            return redirect('listar-clientes')  # Redireciona para a listagem após salvar
    else:
        form = ClienteForm(instance=cliente)

    return render(request, 'clientes/editar-cliente.html', {'form': form, 'cliente': cliente})