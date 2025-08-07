from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, logout
from django.contrib.auth import login as login_django
from django.contrib.auth.decorators import login_required

from django.db.models import Case, When, Value, IntegerField

from tickets.models import Ticket 

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
    tickets = Ticket.objects.filter(usuario=usuario.pk, status__in=["L", "A"]).annotate(
    custom_order=Case(
        When(status='L', then=Value(0)),
        When(status='A', then=Value(1)),
        output_field=IntegerField(),
    )
    ).order_by('custom_order')

    tickets_total = Ticket.objects.filter(usuario=usuario.pk).count()

    context = {
        'tickets': tickets,
        'tickets_total':tickets_total,
    }

    return render(request, 'home/dashboard.html', context)
