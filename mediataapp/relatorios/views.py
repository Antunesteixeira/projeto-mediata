from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from rolepermissions.checkers import has_role
from tickets.models import Ticket

@login_required
def relatorio_view(request):
    #return redirect('dashboard')    
    if has_role(request.user, 'gerente'):
        tickets = Ticket.objects.all()
    else: 
        tickets = Ticket.objects.filter(usuario=request.user)
    
    return render(request, 'relatorios/index-relatorios.html', {'tickets': tickets})