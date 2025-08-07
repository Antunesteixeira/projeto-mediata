from decimal import Decimal
import json

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F, ExpressionWrapper, DecimalField, Sum
from django.shortcuts import get_object_or_404, redirect, render

from django.http import HttpResponse, HttpResponseBadRequest

from .models import Ticket, Orcamento, ItemOrcamento, Insumos, HistoricoTicket, Pagamentos  # ajuste se estiver em outro lugar
from .forms import OrcamentoForm, ItemOrcamentoForm, TicketForm, HistorcoTicketForm, PagamentoForm  # importe só os forms que usa

from django.db.models import ProtectedError

from django.db import IntegrityError

@login_required
def tickets(request):
    usuario = request.user
    tickets = Ticket.objects.filter(usuario=usuario.pk).order_by('-data_criacao')

    context = {
        'tickets': tickets,
    }

    return render(request, 'tickets/index-tickets.html', context)


@login_required
def cadastro_ticket(request):
    if request.method == 'POST':
        form = TicketForm(request.POST)
        if form.is_valid():
            try:
                ticket = form.save(commit=False)
                ticket.usuario = request.user
                ticket = form.save()  # se precisar manipular data_finalizar, faça antes do save com commit=False
                
                messages.success(request, "Ticket cadastrado! Deseja vincular um colaborador agora?")
                return redirect('index-tickets')
            except IntegrityError as e:
                # tenta detectar duplicidade, mas você pode afinar com base no constraint name
                if 'unique' in str(e).lower():
                    messages.error(request, "O número de ticket que está tentando cadastrar já existe.")
                else:
                    messages.error(request, "Erro ao salvar o ticket. Tente novamente.")
        else:
            # o form inválido cai aqui e será renderizado com os erros
            messages.error(request, "Verifique os campos preenchidos.")
    else:
        form = TicketForm()

    return render(request, 'tickets/cadastro-ticket.html', {'form': form})


@login_required
def exibirticket(request, key):
    ticket = get_object_or_404(Ticket, key=key)

    insumos = list(Insumos.objects.values('id', 'insumo', 'codigo', 'tipo', 'valor_unit'))
    for insumo in insumos:
        insumo['valor_unit'] = str(insumo['valor_unit'])

    orcamento = Orcamento.objects.filter(ticket_orcamento=ticket).first()

    form = OrcamentoForm(prefix='orcamento')
    itemorcamento = ItemOrcamentoForm(prefix='itemorcamento')
    ticketformstatus = TicketForm()
    pagamento = PagamentoForm(prefix='form-pagamento')

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        try:
            with transaction.atomic():
                if form_type == 'orcamento':
                    form = OrcamentoForm(request.POST, prefix='orcamento')
                    if form.is_valid():
                        orcamento = form.save(commit=False)
                        orcamento.ticket_orcamento = ticket
                        orcamento.save()
                        return redirect('exibir-ticket', key=ticket.key)
                    else:
                        messages.error(request, "Erro ao salvar orçamento.")
                elif form_type == 'itemorcamento':
                    if not orcamento:
                        messages.error(request, "Crie primeiro um orçamento antes de adicionar itens.")
                    else:
                        itemorcamento = ItemOrcamentoForm(request.POST, prefix='itemorcamento')
                        if itemorcamento.is_valid():
                            item = itemorcamento.save(commit=False)
                            item.orcamento = orcamento
                            # se você armazena subtotal no modelo, calcule aqui; caso contrário a annotate abaixo cuidará
                            try:
                                quantidade = getattr(item, 'quant', 0) or 0
                                valor_unitario = getattr(item.item, 'valor_unit', Decimal('0')) or Decimal('0')  # ajuste se o campo for outro
                                item.subtotal = quantidade * valor_unitario  # apenas se existir esse campo
                            except Exception:
                                pass
                            item.save()
                            return redirect('exibir-ticket', key=ticket.key)
                        else:
                            messages.error(request, "Erro ao salvar item de orçamento.")
                elif form_type == 'form-pagamento':
                    pagamento = PagamentoForm(request.POST, prefix="form-pagamento")
                    if pagamento.is_valid():
                        pag = pagamento.save(commit=False)
                        pag.ticket_pagamento = ticket
                        pag.save()
                        messages.info(request, "Pagamento realizado!")
                        return redirect('exibir-ticket', key=ticket.key)
        except Exception:
            messages.error(request, "Ocorreu um erro ao processar a requisição.")

    # recarregar orçamento
    orcamento = Orcamento.objects.filter(ticket_orcamento=ticket).first()
    list_pagamento = Pagamentos.objects.filter(ticket_pagamento=ticket.id)

    if orcamento:
        # anotando subtotal = quant * item__valor_unit (ajuste nome do campo de valor se for diferente)
        itens_orcamento = ItemOrcamento.objects.filter(orcamento=orcamento).annotate(
            subtotal=ExpressionWrapper(
                F('quant') * F('item__valor_unit'),
                output_field=DecimalField(max_digits=18, decimal_places=2)
            )
        )
        total_itens = itens_orcamento.aggregate(total=Sum('subtotal'))['total'] or Decimal('0')
    else:
        itens_orcamento = ItemOrcamento.objects.none()
        total_itens = Decimal('0')

    valor_custo_total = ticket.func_valor_custo_total()
    bdi = ticket.func_bdi()
    historico = HistoricoTicket.objects.filter(ticket_historico=ticket.id)
    context = {
        'ticket': ticket,
        'valor_custo_total': valor_custo_total,
        'bdi': bdi,
        'form': form,
        'orcamento': orcamento,
        'itemorcamento': itemorcamento,
        'itens_orcamento': itens_orcamento,
        'total_itens': total_itens,
        'historico': historico,
        'ticketformstatus': ticketformstatus,
        'pagamento': pagamento,
        'list_pagamento': list_pagamento,
        #'insumos_json': json.dumps(insumos),
    }
    return render(request, 'tickets/ticket.html', context)

@login_required
def editar_ticket(request, key):
    ticket = get_object_or_404(Ticket, key=key)

    form = TicketForm(request.POST or None, instance=ticket)

    if form.is_valid():
        # Verifica se os dados do formulário foram alterados
        if form.has_changed(): 
            ticket = form.save(commit=False)
            ticket.save()
            messages.success(request, "O Ticket atualizado com sucesso!")
        else:
            messages.info(request, "Nenhuma alteração foi detectada.")
            
        return redirect('index-tickets')

    context = {
        'form': form,
        'ticket': ticket,
    }

    return render(request, 'tickets/editar-ticket.html', context)


def selecionar_ticket(request):
    tickets = Ticket.objects.all()
    return render(request, 'index.html', {'tickets': tickets})

def buscar_tickets(request):
    tickets = list(Ticket.objects.values('id', 'ticket'))
    return render(request, 'index.html', {
        'tickets_json': json.dumps(tickets)  # <- agora é JSON válido
    })

@login_required
def deletar_ticket(request, key):
    ticket = get_object_or_404(Ticket, key=key)

    # opcional: checar permissão extra, ex:
    # if not request.user.has_perm('app.delete_ticket'):
    #     messages.error(request, "Você não tem permissão para excluir este ticket.")
    #     return redirect('exibir-ticket', key=key)

    try:
        ticket.delete()
        messages.success(request, f"Ticket #{ticket.ticket} deletado com sucesso.")
    except ProtectedError:
        messages.error(request, "Não foi possível deletar o ticket porque há objetos relacionados protegendo-o.")
    return redirect('index-tickets') 

def deletar_itemorcamento(request, id, key):
    itemorcamento =  get_object_or_404(ItemOrcamento, id=id)

    try:
        itemorcamento.delete()
        messages.success(request, f"Item #{itemorcamento.item} deletado com sucesso.")
    except ProtectedError:
        messages.error(request, "Não foi possível deletar o ticket porque há objetos relacionados protegendo-o.")
    return redirect('exibir-ticket', key)

@login_required
def update_historico(request, key):
    STATUS_DICT = dict(Ticket.STATUS_CHOICES)
    ticket = get_object_or_404(Ticket, key=key)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status is None:
            # lidar com erro (ex.: reexibir com mensagem)
            return redirect('exibir-ticket', key)

        with transaction.atomic():
            old_status = ticket.status
            ticket.status = new_status
            messages.success(request, "Status alterado com sucesso.")
            ticket.save(update_fields=['status'])

            old_label = STATUS_DICT.get(old_status, old_status)
            new_label = STATUS_DICT.get(new_status, new_status)

            safe_old = old_label.replace("'", "’")
            safe_new = new_label.replace("'", "’")


            HistoricoTicket.objects.create(
                ticket_historico=ticket,
                descricao_historico = f"Status alterado de {safe_old} para {safe_new}"
            )

        return redirect('exibir-ticket', key)  # ou 'meuapp:exibir-tickets' se tiver namespace

    # GET: mostrar formulário/modal
    return redirect('exibir-ticket', key)

def teste(request):
    return render(request, 'index.html')