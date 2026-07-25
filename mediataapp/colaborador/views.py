from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import ColaboradorForm
from .models import Colaborador
from django.contrib.auth.decorators import login_required
from usuarios.forms import CustomUserCreationForm

@login_required
def criar_usuario_para_colaborador(request, colaborador_id):
    colaborador = get_object_or_404(Colaborador, pk=colaborador_id)
    if colaborador.user:
        messages.error(request, 'Este colaborador já possui um usuário vinculado.')
        return redirect('perfil_colaborador', id=colaborador.id)

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            group = form.cleaned_data.get('group')
            if group:
                user.groups.add(group)
            colaborador.user = user
            colaborador.save(update_fields=['user'])
            messages.success(request, f'Usuário {user.username} criado e vinculado ao colaborador.')
            return redirect('perfil_colaborador', id=colaborador.id)
    else:
        initial_data = {'email': colaborador.email} if colaborador.email else {}
        form = CustomUserCreationForm(initial=initial_data)

    return render(
        request,
        'colaboradores/criar_usuario.html',
        {'form': form, 'colaborador': colaborador},
    )


@login_required
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

@login_required
def lista_colaboradores(request):
    colaboradores = Colaborador.objects.all()
    return render(request, 'colaboradores/listar_colaboradores.html', {'colaboradores': colaboradores})

@login_required
def editar_colaborador(request, colaborador_id):
    colaborador = get_object_or_404(Colaborador, id=colaborador_id)

    if request.method == 'POST':
        form = ColaboradorForm(request.POST, instance=colaborador)
        if form.is_valid():
            form.save()
            messages.success(request, "Colaborador editado com sucesso!")
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

# views.py
def perfil_colaborador(request, id):
    colaborador = get_object_or_404(Colaborador, id=id)
    context = {
        'colaborador': colaborador,
    }
    return render(request, 'colaboradores/perfil-colaborador.html', context)
