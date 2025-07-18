from django.shortcuts import render, redirect
from django.contrib.auth.models import User

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
