from django.shortcuts import render, redirect, HttpResponse

from django.shortcuts import get_object_or_404

from .models import Ticket, Orcamento, Servico, Material
from .forms import TicketForm, OrcamentoForm, ServicoForm, MaterialForm

from django.utils import timezone

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
            data_finalizar = form.cleaned_data['data_finalizar'] 
            #return HttpResponse(data_finalizar)
            ticket = form.save(commit=False)
            #ticket.data_finalizar = data_finalizar  # opcional, se quiser manipular
            ticket.save()
            messages.add_message(request, messages.SUCCESS, "Ticket cadastrado! Deseja vincular um colaborador agora?")
            return redirect('index-tickets')
        else:
            messages.add_message(request, messages.ERROR, "O número de Ticket que esta tentando cadastrar já existe!")
            return redirect('cadastro-ticket')
    else:
        form = TicketForm()
    
    context = {
        'form': form,
    } 

    return render(request, 'tickets/cadastro-ticket.html', context)
   
def exibirticket(request, key):
    ticket = get_object_or_404(Ticket, key=key)

    if request.method == 'POST':
        form =  OrcamentoForm(request.POST)
        if form.is_valid():
            orcamento = form.save(commit=False)
            orcamento.ticket_orcamento = ticket  # <-- automático
            orcamento.save()
            return redirect('index-tickets')

    
    valor_custo_total = ticket.func_valor_custo_total()
    bdi = ticket.func_bdi()

    orcamento = Orcamento.objects.filter(ticket_orcamento=ticket).first()

    if orcamento:
        servicos = Servico.objects.filter(orcamento_servico=orcamento.pk)
        materiais = Material.objects.filter(orcamento_material=orcamento.pk)
    else:
        servicos = []  # ou None, depende do que seu template espera
        materiais = []

    #servicos = Servico.objects.filter(orcamento_servico=orcamento.pk).first()
    #materiais = Material.objects.filter(orcamento_material=orcamento.pk).first()
    form = OrcamentoForm()
    formservico = ServicoForm()
    formmaterial = MaterialForm()

    if request.method == 'POST':
        formservico =  ServicoForm(request.POST)
        if formservico.is_valid():
            servicos = formservico.save(commit=False)
            servicos.orcamento_servico = orcamento  # <-- automático
            servicos.save()
            return redirect('index-tickets')
        
    if request.method == 'POST':
        formmaterial = MaterialForm(request.POST)
        if formmaterial.is_valid():
            material = formmaterial.save(commit=False)
            material.orcamento_material = orcamento
            material.save()
            return redirect('index-tickets')


    context = {
        'ticket':ticket,
        'valor_custo_total':valor_custo_total,
        'bdi': bdi,
        'form': form,
        'orcamento': orcamento,
        'servicos': servicos,
        'materiais': materiais,
        'formservico': formservico,
        'formmaterial': formmaterial,
    }
    return render(request, 'tickets/ticket.html', context)

def editar_ticket(request, key):
    ticket = get_object_or_404(Ticket, key=key)
    
    form = TicketForm(request.POST or None, instance=ticket)

    if form.is_valid():
        ticket = form.save(commit=False)

        

        ticket.save()
        return redirect('index-tickets')

    context = {
        'form': form,
        'ticket': ticket,
    }

    return render(request, 'tickets/editar-ticket.html', context)