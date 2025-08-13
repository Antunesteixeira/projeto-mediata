from django.shortcuts import render, get_object_or_404, redirect, HttpResponse
from django.contrib.auth.models import User

from django.contrib import messages

from .forms import CustomUserCreationForm

from rolepermissions.roles import assign_role

from django.contrib.auth.models import Group

from .forms import CustomUserEditForm

def usuarios(request):
    usuarios = User.objects.all()
    context = {
        'usuarios':usuarios,
    }
    return render(request, 'usuarios/index-usuarios.html', context)

# Create your views here.
def cadastro_usuarios(request):
    if request.method == 'GET':
        return render(request, 'usuarios/cadastro-usuarios.html')
    else:
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')

        user = User.objects.filter(username=username).first()

        if user: 
            return redirect('cadastro-usuarios')

def editar_usuarios(request, id):
    return render(request, 'usuarios/editar-usuarios.html')
        
def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            group = form.cleaned_data.get('group')
            if group:
                #assign_role(user, group)
                user.groups.add(group)
            messages.success(request, 'Usuário cadastrado com sucesso!')
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'usuarios/cadastro-usuarios.html', {'form': form})

def editar_usuario(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        form = CustomUserEditForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save(commit=False)
            user.save()

            # Atualizar grupos (limpar e adicionar o selecionado)
            user.groups.clear()
            grupo = form.cleaned_data.get('groups')
            if grupo:
                user.groups.add(grupo)

            messages.success(request, 'Usuário atualizado com sucesso.')
            return redirect('index-usuarios')
    else:
        # Pré-preencher o grupo atual, se houver
        grupo_atual = user.groups.first()
        initial = {'groups': grupo_atual} if grupo_atual else {}
        form = CustomUserEditForm(instance=user, initial=initial)

    return render(request, 'usuarios/editar-usuario.html', {
        'form': form,
        'usuario': user
    })

def perfil_usuario(request, id):
    return render(request, 'usuarios/perfil-usuario.html')