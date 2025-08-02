from django.shortcuts import render, redirect
from django.contrib.auth.models import User

from django.contrib import messages

from .forms import CustomUserCreationForm

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
            form.save()
            messages.success(request, 'Usuário cadastrado com sucesso!')
            return redirect('login')  # ou redirecione para onde quiser
    else:
        form = CustomUserCreationForm()
    return render(request, 'usuarios/cadastro-usuarios.html', {'form': form})
