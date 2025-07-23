from django.shortcuts import render, redirect

from .models import Ticket
from .forms import TicketForm

from django.contrib import messages

def tickets(request):
    tickets = Ticket.objects.all()

    context = {
        'tickets': tickets,
    }

    return render(request, 'tickets/index-tickets.html', context)

def cadastro_ticket(request):
    if request.method == 'POST':
        form = TicketForm(request.POST)
        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS, "Ticket cadastrado! Deseja vincular um colaborador agora?")
            return redirect('index-tickets')
    else:
        form = TicketForm()
    
    context = {
        'form': form,
    } 

    return render(request, 'tickets/cadastro-ticket.html', context)
        