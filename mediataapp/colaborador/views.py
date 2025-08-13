from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import ColaboradorForm
from .models import Colaborador

from django.contrib.auth.decorators import login_required

from django.contrib import messages


def cadastrar_colaborador(request):
    if request.method == "POST":
        form = ColaboradorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Colaborador cadastrado com sucesso!")
            return redirect('lista_colaboradores')
        else:
            messages.error(request, "Erro ao cadastrar colaborador. Verifique os campos.")
    else:
        form = ColaboradorForm()

    return render(request, 'colaboradores/cadastrar.html', {'form': form})

def lista_colaboradores(request):
    colaboradores = Colaborador.objects.all()
    return render(request, 'colaboradores/listar_colaboradores.html', {'colaboradores': colaboradores})

def editar_colaborador(request, colaborador_id):
    colaborador = get_object_or_404(Colaborador, id=colaborador_id)

    if request.method == 'POST':
        form = ColaboradorForm(request.POST, instance=colaborador)
        if form.is_valid():
            form.save()
            return redirect('lista_colaboradores')  # Redireciona para a listagem após salvar
    else:
        form = ColaboradorForm(instance=colaborador)

    return render(request, 'colaboradores/editar-colaborador.html', {'form': form, 'colaborador': colaborador})

@login_required
def deletar_colaborador(request, colaborador_id):
    colaborador = get_object_or_404(Colaborador, pk=colaborador_id)
    if request.method == "POST":
        nome = str(colaborador)  # ou cliente.nome, conforme seu modelo
        colaborador.delete()
        messages.success(request, f"Colaborador '{nome}' deletado com sucesso.")
        return redirect('lista_colaboradores')  # ajuste para a rota da lista de clientes
    # GET -> mostrar página de confirmação
    return render(request, 'colaboradores/listar_colaboradores.html', {'colaborador': colaborador})