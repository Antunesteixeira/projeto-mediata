from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, logout
from django.contrib.auth import login as login_django
from django.contrib.auth.decorators import login_required

from django.db.models import Case, When, Value, IntegerField
from django.http import Http404
from tickets.models import Ticket 

from rolepermissions.checkers import has_role

from django.contrib.auth.models import User, Group


@login_required
def index(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    else:
        return redirect('/accounts/login/')
    
def login(request):
    if request.method == "GET":
        if request.user.is_authenticated:
            return redirect('/dashboard/')
        else:
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
        
@login_required
def sair(request):
    logout(request)
    return redirect('/')

@login_required
def dashboard(request):
    usuario = request.user

    tickets = Ticket.objects.filter(
        usuario=usuario,  # pode passar o objeto direto, não precisa do `.pk`
        status__in=["V", "X", "E", "A"]
    ).annotate(
        custom_order=Case(
            When(status='L', then=Value(0)),
            When(status='A', then=Value(1)),
            default=Value(2),  # evita erro caso status não esteja listado
            output_field=IntegerField(),
        )
    ).order_by('custom_order')

    if has_role(usuario, [User, 'gerente']):
        tickets_total = Ticket.objects.all().count()
    else:
        tickets_total = Ticket.objects.filter(usuario=usuario).count()

    context = {
        'tickets': tickets,
        'tickets_total': tickets_total,
    }

    return render(request, 'home/dashboard.html', context)

def erro_404(request, exception):
    return render(request, '404.html', status=404)
