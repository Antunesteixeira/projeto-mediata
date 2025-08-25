from decimal import Decimal
import json
import uuid
from django.utils import timezone
from django.views.decorators.http import require_POST

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F, ExpressionWrapper, DecimalField, Sum
from django.shortcuts import get_object_or_404, redirect, render

from django.contrib.auth.models import User, Group
from colaborador.models import Colaborador
from clientes.models import Cliente
from core.models import Empresa

from django.http import HttpResponse, HttpResponseBadRequest

from .models import Ticket, Orcamento, ItemOrcamento, Insumos, HistoricoTicket, Pagamentos  # ajuste se estiver em outro lugar
from .forms import OrcamentoForm, ItemOrcamentoForm, TicketForm, HistorcoTicketForm, PagamentoForm  # importe só os forms que usa

from rolepermissions.checkers import has_role

from django.db.models import ProtectedError

from django.db import IntegrityError

import os
from django.conf import settings

from django.template.loader import get_template
from xhtml2pdf import pisa
from datetime import datetime

@login_required
def tickets(request):
    usuario = request.user
    
    if has_role(usuario, [User, 'gerente']):
        tickets = Ticket.objects.all().order_by('-data_criacao')
    else:
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
                
                messages.success(request, "Ticket cadastrado com sucesso!")
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

    return render(request, 'tickets/editar-ticket.html', {'form': form})


@login_required
def exibirticket(request, key):
    ticket = get_object_or_404(Ticket, key=key)
    # No início da view (junto com os outros forms):
    pagamento = PagamentoForm(prefix='pagamento')  # Mude o prefix para ser único

    insumos = list(Insumos.objects.values('id', 'insumo', 'valor_unit'))
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
                        # Verifique os dados recebidos
                        print("Dados recebidos:", request.POST)  # Para debug
                        
                        item_id = request.POST.get('item')
                        quantidade = request.POST.get('quant')
                        
                        # Validações básicas
                        if not item_id or not quantidade:
                            messages.error(request, "Dados incompletos para o item de orçamento.")
                            return redirect('exibir-ticket', key=ticket.key)
                        
                        try:
                            # Crie o item de orçamento manualmente
                            item_orcamento = ItemOrcamento(
                                orcamento=orcamento,
                                item_id=item_id,
                                quant=int(quantidade)
                            )
                            item_orcamento.save()
                            messages.success(request, "Item adicionado com sucesso!")
                            return redirect('exibir-ticket', key=ticket.key)
                            
                        except Insumos.DoesNotExist:
                            messages.error(request, "Insumo não encontrado.")
                        except Exception as e:
                            messages.error(request, f"Erro ao salvar item: {str(e)}")
                    
                    return redirect('exibir-ticket', key=ticket.key)
                if form_type == 'form-pagamento':
        
                    valor = request.POST.get('valor_pagamento')
                    data = request.POST.get('data_pagamento')
                    status = 'status_pagamento' in request.POST
                    
                    # Validação básica
                    if not all([valor, data]):
                        messages.error(request, "Preencha todos os campos obrigatórios!")
                    else:
                        Pagamentos.objects.create(
                            ticket_pagamento=ticket,
                            tipo=request.POST.get('tipo'),
                            valor_pagamento=valor,
                            data_pagamento=data,
                            status_pagamento=status
                        )
                        messages.success(request, "Pagamento adicionado com sucesso!")
                        return redirect('exibir-ticket', key=ticket.key)
                
        except Exception:
            messages.error(request, "Ocorreu um erro ao processar a requisição.")

    # recarregar orçamento
    orcamento = Orcamento.objects.filter(ticket_orcamento=ticket).first()
    list_pagamento = Pagamentos.objects.filter(ticket_pagamento=ticket.id)

    if orcamento:
        itens_orcamento = ItemOrcamento.objects.filter(orcamento=orcamento).annotate(
            subtotal=ExpressionWrapper(
                F('quant') * F('item__valor_unit'),
                output_field=DecimalField(max_digits=18, decimal_places=2)
            )
        )
        total_itens = itens_orcamento.aggregate(total=Sum('subtotal'))['total'] or Decimal('0')
        orcamento.valor_total = total_itens
        orcamento.save()
    else:
        itens_orcamento = ItemOrcamento.objects.none()
        total_itens = Decimal('0')
        

    # Calcular resumo de pagamentos por tipo
    resumo_pagamentos = {
        'M': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},  # Material
        'S': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},  # Serviço
        'O': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},  # Mão de Obra
        'E': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},  # Equipamento
        'T': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},  # Taxa
    }
    
    # Calcular totais orçados por tipo
    if itens_orcamento:
        for item in itens_orcamento:
            tipo = item.item.tipo
            if tipo in resumo_pagamentos:
                resumo_pagamentos[tipo]['total_orcado'] += item.subtotal
    
    # Calcular totais pagos e pendentes por tipo
    if list_pagamento:
        for pagamento in list_pagamento:
            tipo = pagamento.tipo
            if tipo in resumo_pagamentos:
                if pagamento.status_pagamento:
                    resumo_pagamentos[tipo]['total_pago'] += pagamento.valor_pagamento
                else:
                    resumo_pagamentos[tipo]['total_pendente'] += pagamento.valor_pagamento
    
    # Calcular saldos
    for tipo in resumo_pagamentos:
        resumo_pagamentos[tipo]['saldo'] = (
            resumo_pagamentos[tipo]['total_orcado'] - 
            resumo_pagamentos[tipo]['total_pago'] - 
            resumo_pagamentos[tipo]['total_pendente']
        )
    
    # Calcular totais gerais
    resumo_geral = {
        'total_orcado': sum(v['total_orcado'] for v in resumo_pagamentos.values()),
        'total_pago': sum(v['total_pago'] for v in resumo_pagamentos.values()),
        'total_pendente': sum(v['total_pendente'] for v in resumo_pagamentos.values()),
        'saldo': sum(v['saldo'] for v in resumo_pagamentos.values()),
    }

    valor_custo_total = resumo_geral['total_orcado'] - resumo_geral['total_pago'] if resumo_geral['total_pago'] else Decimal('0')

    bdi = ticket.func_bdi()
    
    if resumo_geral['saldo'] != 0:
        margem = resumo_geral['total_orcado'] / resumo_geral['total_pago'] if resumo_geral['total_pago'] != 0 else Decimal('0')
    else:
        margem = Decimal('0')
    historico = HistoricoTicket.objects.filter(ticket_historico=ticket.id)
    
    context = {
        'ticket': ticket,
        'valor_custo_total': valor_custo_total,
        'bdi': bdi,
        'form': form,
        'margem': margem,
        'orcamento': orcamento,
        'itemorcamento': itemorcamento,
        'itens_orcamento': itens_orcamento,
        'total_itens': total_itens,
        'historico': historico,
        'ticketformstatus': ticketformstatus,
        'pagamento': pagamento,
        'list_pagamento': list_pagamento,
        'resumo_pagamentos': resumo_pagamentos,
        'resumo_geral': resumo_geral,
        'insumos_json': json.dumps(insumos, ensure_ascii=False),
        'MEDIA_URL': settings.MEDIA_URL,
    }
    #return HttpResponse(json.dumps(insumos, ensure_ascii=False))
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

@login_required
def selecionar_ticket(request):
    tickets = Ticket.objects.all()
    return render(request, 'index.html', {'tickets': tickets})

@login_required
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

@login_required
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

@login_required
def deletar_pagamento(request, id, key):
    pagamento =  get_object_or_404(Pagamentos, id=id)

    try:
        pagamento.delete()
        messages.success(request, f"Pagamento deletado com sucesso.")
    except ProtectedError:
        messages.error(request, "Não foi possível deletar o pagamento porque há objetos relacionados protegendo-o.")
    return redirect('exibir-ticket', key)

@login_required
def addTicketColaborador(request, id_ticket):
    usuario = request.user
    if request.method == 'GET':
        colaboradores = Colaborador.objects.all()

    origem = request.GET.get('origem', None)

    context = {
        'colaboradores':colaboradores, 
        'id_ticket':id_ticket,
        'title': 'Adicionar Colaborador ao Ticket',
        'origem': origem,
    }
    return render(request, 'tickets/add-colaborador-ticket.html', context)

@login_required
def cadastrarColaboradorTicket(request, id_ticket, id_colaborador):
    if request.method == 'GET':
        # Obtém o ticket ou retorna 404 se não existir
        ticket = get_object_or_404(Ticket, id=id_ticket)
        
        # Obtém o colaborador ou retorna 404 se não existir
        col = get_object_or_404(Colaborador, id=id_colaborador)

        # Associa o colaborador ao ticket
        ticket.colaborador = col
        ticket.save()
    
        messages.add_message(request, messages.INFO, f"O Colaborador: {ticket.colaborador} foi adicionado ao Ticket: {ticket.ticket} com sucesso!")
        #return HttpResponse(request.POST['editar-colaborador'] == 'editar-colaborador')
        
        return redirect('index-tickets')
    
@login_required    
def addTicketCliente(request, id_ticket):
    usuario = request.user
    if request.method == 'GET':
        clientes = Cliente.objects.all()    
    
    return render(request, 'tickets/add-cliente-ticket.html', {'clientes':clientes, 'id_ticket':id_ticket})

@login_required
def cadastrarTicketCliente(request, id_cliente, id_ticket):
    if request.method == 'GET':
        # Obtém o ticket ou retorna 404 se não existir
        ticket = get_object_or_404(Ticket, id=id_ticket)
        
        # Obtém o cliente ou retorna 404 se não existir
        cli = get_object_or_404(Cliente, id=id_cliente)

        # Associa o clinete ao ticket
        ticket.cliente = cli
        ticket.save()
    
        messages.add_message(request, messages.INFO, f"O Clinete: {ticket.cliente} foi adicionado ao Ticket: {ticket.ticket} com sucesso!")

        return redirect('index-tickets')

@login_required
def editar_pagamento(request, pagamento_id, key):
    pagamento = get_object_or_404(Pagamentos, id=pagamento_id)
    ticket = get_object_or_404(Ticket, key=key)

    if request.method == 'POST':
        form = PagamentoForm(request.POST, instance=pagamento)
        if form.is_valid():
            pagamento.data_update_pagamento = timezone.now()
            form.save()
            messages.success(request, "Pagamento atualizado com sucesso!")
            return redirect('exibir-ticket', key=ticket.key)
        # Se o formulário for inválido, vai continuar para renderizar o template com erros
    else:
        form = PagamentoForm(instance=pagamento)

    return render(request, 'seu_template.html', {
        'form': form,
        'pagamento': pagamento,
        'ticket': ticket
    })

@login_required
def add_pagamento(request, key):
    ticket = get_object_or_404(Ticket, key=key)
    if request.method == 'POST':
        form = PagamentoForm(request.POST)
        if form.is_valid():
            pagamento = form.save(commit=False)
            pagamento.ticket_pagamento = ticket  # Corrija aqui!
            pagamento.save()
            messages.success(request, "Pagamento adicionado com sucesso!")
            return redirect('exibir-ticket', key=ticket.key)
    else:
        form = PagamentoForm()
    return render(request, 'tickets/ticket.html', {
        'form': form,
        'ticket': ticket,
        # inclua outros contextos necessários
    })


@login_required
@require_POST
def upload_nfe(request, key):
    ticket = get_object_or_404(Ticket, key=key)
    if request.method == 'POST' and request.FILES.get('arquivo'):
        arquivo = request.FILES['arquivo']
        extensao = os.path.splitext(arquivo.name)[1].lower()  # pega a extensão do arquivo e deixa minúscula
        tipos_permitidos = ['.jpg', '.jpeg', '.png', '.pdf']

        if extensao not in tipos_permitidos:
            messages.error(request, "Só é permitido enviar imagens (.jpg, .jpeg, .png) ou PDF.")
            return redirect('exibir-ticket', key=key)

        nome_aleatorio = f"{uuid.uuid4().hex}{extensao}"
        pasta_destino = os.path.join(settings.MEDIA_ROOT, 'nfe')
        os.makedirs(pasta_destino, exist_ok=True)
        caminho_arquivo = os.path.join(pasta_destino, nome_aleatorio)
        with open(caminho_arquivo, 'wb+') as destino:
            for chunk in arquivo.chunks():
                destino.write(chunk)
        # Salva apenas o caminho relativo

        ticket.nfe_path = f'nfe/{nome_aleatorio}'
        ticket.save()
        messages.success(request, "Nota Fiscal enviada com sucesso!")
    else:
        messages.error(request, "Selecione um arquivo válido para enviar.")
    return redirect('exibir-ticket', key=key)

@login_required
def delete_nfe(request, key):
    ticket = get_object_or_404(Ticket, key=key)
    
    if ticket.nfe_path:
        # Remove o arquivo físico
        file_path = os.path.join(settings.MEDIA_ROOT, ticket.nfe_path)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                messages.error(request, f"Erro ao remover arquivo: {str(e)}")
                return redirect('exibir-ticket', key=key)
        
        # Limpa o campo no banco de dados
        ticket.nfe_path = None
        ticket.save()
        messages.success(request, "Nota fiscal removida com sucesso!")
    else:
        messages.warning(request, "Não há nota fiscal para remover")
    
    return redirect('exibir-ticket', key=key)

@login_required
@require_POST
def upload_comprovante(request, id, key):
    pagamento = get_object_or_404(Pagamentos, id=id)
    if request.method == 'POST' and request.FILES.get('comprovante'):
        arquivo = request.FILES['comprovante']
        extensao = os.path.splitext(arquivo.name)[1].lower()
        tipos_permitidos = ['.jpg', '.jpeg', '.png', '.pdf']

        if extensao not in tipos_permitidos:
            messages.error(request, "Só é permitido enviar imagens (.jpg, .jpeg, .png) ou PDF.")
            return redirect('exibir-ticket', key=key)

        nome_aleatorio = f"{uuid.uuid4().hex}{extensao}"
        pasta_destino = os.path.join(settings.MEDIA_ROOT, 'comprovantes')
        os.makedirs(pasta_destino, exist_ok=True)
        caminho_arquivo = os.path.join(pasta_destino, nome_aleatorio)
        with open(caminho_arquivo, 'wb+') as destino:
            for chunk in arquivo.chunks():
                destino.write(chunk)

        pagamento.comprovante = f'comprovantes/{nome_aleatorio}'
        pagamento.data_update_pagamento = timezone.now()
        pagamento.save()
        messages.success(request, "Comprovante enviado com sucesso!")
    else:
        messages.error(request, "Selecione um arquivo válido para enviar.")
    return redirect('exibir-ticket', key=key)

@login_required
def delete_comprovante(request, id, key):
    pagamento = get_object_or_404(Pagamentos, id=id)

    if pagamento.comprovante:
        # Remove o arquivo físico
        file_path = os.path.join(settings.MEDIA_ROOT, pagamento.comprovante)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                messages.error(request, f"Erro ao remover arquivo: {str(e)}")
                return redirect('exibir-ticket', key=key)
        
        # Limpa o campo no banco de dados
        pagamento.comprovante = None
        pagamento.save()
        messages.success(request, "Comprovante removido com sucesso!")
    else:
        messages.warning(request, "Não há comprovante para remover")

    return redirect('exibir-ticket', key=key)



def gerar_pdf_orcamento(request, ticket_id):
    try:
        empresa = Empresa.objects.get(id=1)  # Exemplo: pegar a empresa com ID 1
        ticket = Ticket.objects.get(id=ticket_id)
        orcamento = Orcamento.objects.get(ticket_orcamento=ticket)
        itens_orcamento = ItemOrcamento.objects.filter(orcamento=orcamento)
        
        # Calcular subtotal para cada item e total geral
        for item in itens_orcamento:
            # Calcular subtotal manualmente
            item.subtotal_calculado = item.quant * item.item.valor_unit
        
        # Calcular total geral
        total_itens = sum(item.quant * item.item.valor_unit for item in itens_orcamento)
        
        context = {
            'empresa': empresa,
            'ticket': ticket,
            'orcamento': orcamento,
            'itens_orcamento': itens_orcamento,
            'total_itens': total_itens,
            'data_emissao': datetime.now().strftime("%d/%m/%Y %H:%M"),
            'empresa': {
                'nome': 'Sua Empresa',
                'endereco': 'Endereço da Empresa',
                'telefone': '(00) 0000-0000',
                'email': 'contato@empresa.com',
                'cnpj': '00.000.000/0001-00'
            },
            'logo_path': 'img/logo-mediata-5.1.png',
            'has_logo': True,  # ou verifique se o arquivo existe
            'MEDIA_URL': settings.MEDIA_URL,
        }

        template_path = 'tickets/orcamento_pdf.html'
        template = get_template(template_path)
        html = template.render(context)
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="orcamento_{ticket.ticket}.pdf"'
        
        # Criar PDF
        pisa_status = pisa.CreatePDF(html, dest=response)
        
        if pisa_status.err:
            return HttpResponse('Erro ao gerar PDF')
        return response
        
    except Ticket.DoesNotExist:
        return HttpResponse('Ticket não encontrado')
    except Orcamento.DoesNotExist:
        return HttpResponse('Orçamento não encontrado para este ticket')