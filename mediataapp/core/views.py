from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, logout
from django.contrib.auth import login as login_django
from django.contrib.auth.decorators import login_required

def index(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    else:
        return redirect('/accounts/login/')
    
def login(request):
    if request.method == "GET":
        return render(request, 'registration/login.html')
    else: 
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(username=username, password=password)

        if user:
            login_django(request, user)
            return redirect('/dashboard/')
        else:
            return redirect('accounts/login/')

def sair(request):
    logout(request)
    return redirect('/')

@login_required
def dashboard(request):
    return render(request, 'home/dashboard.html')
