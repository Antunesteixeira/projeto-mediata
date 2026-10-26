from decimal import Decimal
import json
import uuid
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F, ExpressionWrapper, DecimalField, Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from colaborador.models import Colaborador
from clientes.models import Cliente
from core.models import Empresa
from usuarios.access import is_assinante
from core.tenancy import (
    tickets_da_empresa, pode_acessar_financeiro, pode_assumir_ticket, pode_consultar_fila,
    pode_gerenciar_empresa,
)
from .access import (
    exigir_empresa, pode_operar_tickets, ticket_de_financeiro, ticket_de_operacao,
)
from django.core.exceptions import PermissionDenied, ValidationError

from django.http import HttpResponse, HttpResponseBadRequest, Http404

from .models import Ticket, Orcamento, ItemOrcamento, Insumos, HistoricoTicket, Pagamentos, Anexo, Recebimentos
from .forms import OrcamentoForm, ItemOrcamentoForm, TicketForm, PagamentoForm, AnexoForm, RecebimentosForm, EditarRecebimentoForm, AssinanteTicketForm

from django.db.models import ProtectedError

from django.db import IntegrityError

import os
from django.conf import settings

from django.template.loader import get_template
from datetime import datetime

from weasyprint import HTML
from num2words import num2words


def _salvar_total_orcamento(orcamento):
    """Atualiza o total ao alterar os itens, sem gravar durante uma consulta."""
    subtotal = ExpressionWrapper(
        F('quant') * F('item__valor_unit'),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )
    orcamento.valor_total = ItemOrcamento.objects.filter(orcamento=orcamento).aggregate(
        total=Sum(subtotal),
    )['total'] or Decimal('0')
    orcamento.save(update_fields=['valor_total'])


def _tickets_disponiveis():
    return Ticket.objects.filter(
        empresa__isnull=True, status='L', usuario__groups__name='assinante', usuario__is_superuser=False,
    ).distinct()


def _contexto_fila(request):
    return {
        'pode_assumir': request.user.is_superuser or pode_assumir_ticket(request.user),
        'empresas': Empresa.objects.filter(ativo=True).order_by('nome_fantasia')
        if request.user.is_superuser else Empresa.objects.none(),
    }


@login_required
@require_http_methods(['GET', 'HEAD'])
def tickets_disponiveis(request):
    if not pode_consultar_fila(request.user):
        raise PermissionDenied('Seu perfil permite consultar apenas os tickets que você cadastrou.')
    exigir_empresa(request.user)
    tickets = _tickets_disponiveis().select_related('usuario').order_by('-data_criacao')
    termo = request.GET.get('q', '').strip()
    if termo:
        tickets = tickets.filter(Q(ticket__icontains=termo) | Q(descricao__icontains=termo))
    contexto = _contexto_fila(request)
    contexto.update(tickets=tickets, termo=termo)
    return render(request, 'tickets/disponiveis.html', contexto)


@login_required
@require_http_methods(['GET', 'HEAD'])
def ticket_disponivel(request, key):
    if not pode_consultar_fila(request.user):
        raise PermissionDenied('Seu perfil permite consultar apenas os tickets que você cadastrou.')
    exigir_empresa(request.user)
    ticket = get_object_or_404(_tickets_disponiveis().select_related('usuario'), key=key)
    contexto = _contexto_fila(request)
    contexto['ticket'] = ticket
    return render(request, 'tickets/ticket-disponivel.html', contexto)


@login_required
@require_POST
def assumir_ticket(request, key):
    if not pode_assumir_ticket(request.user):
        raise PermissionDenied('Somente gerentes podem assumir tickets para a empresa.')
    if request.user.is_superuser:
        empresa_id = request.POST.get('empresa', '')
        if not empresa_id.isdigit():
            return HttpResponseBadRequest('Selecione a empresa responsável pelo ticket.')
        empresa = get_object_or_404(Empresa, pk=empresa_id, ativo=True)
    else:
        empresa = exigir_empresa(request.user)
    with transaction.atomic():
        # A trava serializa a disputa pelo mesmo ticket entre empresas.
        ticket = get_object_or_404(Ticket.objects.select_for_update(), key=key)
        if ticket.empresa_id is not None:
            if ticket.empresa_id == empresa.pk:
                return redirect('exibir-ticket', key=ticket.key)
            return render(request, 'tickets/ticket-indisponivel.html', status=409)
        if ticket.status != 'L' or ticket.usuario_id is None or not is_assinante(ticket.usuario):
            raise Http404('Ticket indisponível.')
        ticket.empresa = empresa
        ticket.assumido_por = request.user
        ticket.assumido_em = timezone.now()
        ticket.save(update_fields=['empresa', 'assumido_por', 'assumido_em'])
        HistoricoTicket.objects.create(
            ticket_historico=ticket,
            descricao_historico=f'Ticket assumido pela empresa {empresa.nome_fantasia}.',
        )
    messages.success(request, 'Ticket assumido com sucesso. Ele agora pertence à sua empresa.')
    return redirect('exibir-ticket', key=ticket.key)


@login_required
def tickets(request):
    if not is_assinante(request.user):
        exigir_empresa(request.user)
    tickets = tickets_da_empresa(request.user).select_related(
        'usuario', 'cliente', 'colaborador', 'empresa', 'assumido_por',
    ).order_by('-data_criacao')
    return render(request, 'tickets/index-tickets.html', {'tickets': tickets})


@login_required
def cadastro_ticket(request):
    subscriber = is_assinante(request.user)
    if not subscriber and not pode_operar_tickets(request.user):
        raise PermissionDenied('Seu perfil permite apenas acompanhar tickets.')
    form_class = AssinanteTicketForm if subscriber else TicketForm
    form_kwargs = {} if subscriber else {'user': request.user}
    if request.method == 'POST':
        form = form_class(request.POST, **form_kwargs)
        if form.is_valid():
            try:
                ticket = form.save(commit=False)
                ticket.usuario = request.user
                if subscriber:
                    ticket.status = 'L'
                    ticket.empresa = None
                elif not request.user.is_superuser:
                    ticket.empresa = exigir_empresa(request.user)
                if not subscriber:
                    ticket.assumido_por = request.user
                    ticket.assumido_em = timezone.now()
                ticket.save()
                
                messages.success(request, "Ticket cadastrado com sucesso!")
                return redirect('index-tickets')
            except ValidationError as error:
                form.add_error('ticket', error)
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
        form = form_class(**form_kwargs)

    template = 'tickets/cadastro-ticket.html' if subscriber else 'tickets/editar-ticket.html'
    return render(request, template, {'form': form})


@login_required
def exibirticket(request, key):
    if is_assinante(request.user) or not pode_operar_tickets(request.user):
        if request.method not in ('GET', 'HEAD'):
            raise PermissionDenied('O acompanhamento do ticket permite apenas consulta.')
        if not is_assinante(request.user):
            exigir_empresa(request.user)
        ticket = get_object_or_404(tickets_da_empresa(request.user).select_related(
            'cliente', 'colaborador', 'empresa', 'assumido_por',
        ), key=key)
        historico = HistoricoTicket.objects.filter(ticket_historico=ticket).order_by('-data_historico', '-pk')
        return render(request, 'tickets/acompanhamento-ticket.html', {
            'ticket': ticket,
            'historico': historico,
        })
    ticket = ticket_de_operacao(request, key=key)

    if not pode_acessar_financeiro(request.user):
        if request.method not in ('GET', 'HEAD'):
            raise PermissionDenied('Seu perfil permite apenas as operações não financeiras do ticket.')
        return render(request, 'tickets/ticket.html', {
            'ticket': ticket,
            'historico': HistoricoTicket.objects.filter(ticket_historico=ticket),
            'ticketformstatus': TicketForm(instance=ticket, user=request.user),
            'pode_acessar_financeiro': False,
        })

    anexos = Anexo.objects.filter(ticket_anexo=ticket)
    
    # Buscar orçamento existente
    orcamento = Orcamento.objects.filter(ticket_orcamento=ticket).first()

    # Lista de recebimentos do ticket
    recebimentos = Recebimentos.objects.filter(ticket_recebimento=ticket).order_by('-data_recebimento')
    
    # Inicializar forms com valores padrão
    form = OrcamentoForm(prefix='orcamento')
    itemorcamento = ItemOrcamentoForm(prefix='itemorcamento')
    itemorcamento.fields['item'].queryset = Insumos.objects.filter(empresa=ticket.empresa)
    ticketformstatus = TicketForm(instance=ticket, user=request.user)
    pagamento_form = PagamentoForm()
    anexo_form = AnexoForm()
    recebimentos_form = RecebimentosForm()  # ← sem prefixo

    # Preparar dados dos insumos para JSON (usado em algum lugar do template)
    insumos = list(Insumos.objects.filter(empresa=ticket.empresa).values('id', 'insumo', 'valor_unit'))
    for insumo in insumos:
        insumo['valor_unit'] = str(insumo['valor_unit'])
    
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
                        messages.success(request, "Orçamento criado com sucesso!")
                        return redirect('exibir-ticket', key=ticket.key)
                    else:
                        messages.error(request, "Erro ao salvar orçamento. Verifique os campos.")
                
                elif form_type == 'itemorcamento':
                    if not orcamento:
                        messages.error(request, "Crie primeiro um orçamento antes de adicionar itens.")
                    else:
                        item_id = request.POST.get('item')
                        quantidade = request.POST.get('quant')
                        
                        if not item_id or not quantidade:
                            messages.error(request, "Dados incompletos para o item de orçamento.")
                        else:
                            orcamento = get_object_or_404(
                                Orcamento.objects.select_for_update(),
                                pk=orcamento.pk, ticket_orcamento=ticket,
                            )
                            insumo = get_object_or_404(Insumos, pk=item_id, empresa=ticket.empresa)
                            try:
                                quantidade = quantidade.replace(',', '.')
                                item_orcamento = ItemOrcamento(
                                    orcamento=orcamento,
                                    item=insumo,
                                    quant=Decimal(quantidade)
                                )
                                item_orcamento.save()
                                _salvar_total_orcamento(orcamento)
                                messages.success(request, "Item adicionado com sucesso!")
                                return redirect('exibir-ticket', key=ticket.key)
                            except Insumos.DoesNotExist:
                                messages.error(request, "Insumo não encontrado.")
                            except Exception as e:
                                messages.error(request, f"Erro ao salvar item: {str(e)}")
                    
                    return redirect('exibir-ticket', key=ticket.key)
                
                elif form_type == 'form-pagamento':
                    pagamento_form = PagamentoForm(request.POST)
                    if pagamento_form.is_valid():
                        pagamento = pagamento_form.save(commit=False)
                        pagamento.ticket_pagamento = ticket
                        pagamento.save()
                        messages.success(request, "Pagamento adicionado com sucesso!")
                        return redirect('exibir-ticket', key=ticket.key)
                    messages.error(request, 'Verifique os dados do pagamento.')

                elif form_type == 'anexo':
                    anexo_form = AnexoForm(request.POST, request.FILES)
                    if anexo_form.is_valid():
                        anexo = anexo_form.save(commit=False)
                        anexo.ticket_anexo = ticket
                        anexo.save()
                        messages.success(request, "Anexo adicionado com sucesso!")
                        return redirect('exibir-ticket', key=ticket.key)
                    else:
                        messages.error(request, "Erro ao adicionar anexo. Verifique os campos.")
                        # Não redireciona, continua para mostrar o form com erros
                
                elif form_type == 'recebimentos_form':  # ← nome correspondente ao modal
                    recebimentos_form = RecebimentosForm(request.POST, request.FILES)
                    if recebimentos_form.is_valid():
                        recebimento = recebimentos_form.save(commit=False)
                        recebimento.ticket_recebimento = ticket  # vincula ao ticket atual
                        recebimento.save()
                        messages.success(request, "Recebimento adicionado com sucesso!")
                        return redirect('exibir-ticket', key=ticket.key)
                    else:
                        messages.error(request, "Erro ao adicionar recebimento. Verifique os campos.")
                        # Não redireciona, continua para mostrar o form com erros
                
        except (Http404, PermissionDenied):
            raise
        except Exception as e:
            messages.error(request, f"Ocorreu um erro ao processar a requisição: {str(e)}")
    
    # Recarregar orçamento (pode ter sido criado na mesma requisição, mas como já redirecionamos,
    # isso é útil para o caso de GET ou formulários que não redirecionam)
    orcamento = Orcamento.objects.filter(ticket_orcamento=ticket).first()
    
    # Lista de pagamentos
    list_pagamento = Pagamentos.objects.filter(ticket_pagamento=ticket.id)
    
    # Itens do orçamento e cálculo de total
    if orcamento:
        itens_orcamento = ItemOrcamento.objects.filter(orcamento=orcamento).annotate(
            subtotal=ExpressionWrapper(
                F('quant') * F('item__valor_unit'),
                output_field=DecimalField(max_digits=18, decimal_places=2)
            )
        )
        total_itens = itens_orcamento.aggregate(total=Sum('subtotal'))['total'] or Decimal('0')
        orcamento.valor_total = total_itens
    else:
        itens_orcamento = ItemOrcamento.objects.none()
        total_itens = Decimal('0')
    
    # Resumo de pagamentos por tipo (M, S, O, E, T)
    resumo_pagamentos = {
        'M': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},
        'S': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},
        'O': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},
        'E': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},
        'T': {'total_orcado': Decimal('0'), 'total_pago': Decimal('0'), 'total_pendente': Decimal('0'), 'saldo': Decimal('0')},
    }
    
    if itens_orcamento:
        for item in itens_orcamento:
            tipo = item.item.tipo
            if tipo in resumo_pagamentos:
                resumo_pagamentos[tipo]['total_orcado'] += item.subtotal
    
    if list_pagamento:
        for pagamento in list_pagamento:
            tipo = pagamento.tipo
            if tipo in resumo_pagamentos:
                if pagamento.status_pagamento:
                    resumo_pagamentos[tipo]['total_pago'] += pagamento.valor_pagamento
                else:
                    resumo_pagamentos[tipo]['total_pendente'] += pagamento.valor_pagamento
    
    for tipo in resumo_pagamentos:
        resumo_pagamentos[tipo]['saldo'] = (
            resumo_pagamentos[tipo]['total_orcado'] - 
            resumo_pagamentos[tipo]['total_pago'] - 
            resumo_pagamentos[tipo]['total_pendente']
        )
    
    resumo_geral = {
        'total_orcado': sum(v['total_orcado'] for v in resumo_pagamentos.values()),
        'total_pago': sum(v['total_pago'] for v in resumo_pagamentos.values()),
        'total_pendente': sum(v['total_pendente'] for v in resumo_pagamentos.values()),
        'saldo': sum(v['saldo'] for v in resumo_pagamentos.values()),
    }
    
    valor_custo_total = resumo_geral['total_orcado'] - resumo_geral['total_pago'] if resumo_geral['total_pago'] else Decimal('0')
    bdi = ticket.func_bdi()  # supondo que exista esse método no modelo Ticket
    
    total_pagamentos = resumo_geral['total_pago'] + resumo_geral['total_pendente']
    if total_pagamentos > 0:
        margem = (resumo_geral['total_orcado'] / total_pagamentos)
    else:
        margem = Decimal('0')
    
    historico = HistoricoTicket.objects.filter(ticket_historico=ticket.id)
    
    context = {
        'ticket': ticket,
        'valor_custo_total': valor_custo_total,
        'bdi': bdi,
        'form': form,
        'anexos': anexos,
        'recebimentos': recebimentos,
        'recebimentos_form': recebimentos_form,      # ← agora sem prefixo
        'can_edit_recebimentos': pode_acessar_financeiro(request.user),
        'form_anexo': anexo_form,                    # pode conter erros se for inválido
        'margem': margem,
        'orcamento': orcamento,
        'itemorcamento': itemorcamento,
        'itens_orcamento': itens_orcamento,
        'total_itens': total_itens,
        'historico': historico,
        'ticketformstatus': ticketformstatus,
        'pagamento': pagamento_form,
        'list_pagamento': list_pagamento,
        'resumo_pagamentos': resumo_pagamentos,
        'resumo_geral': resumo_geral,
        'insumos_json': json.dumps(insumos, ensure_ascii=False),
        'MEDIA_URL': settings.MEDIA_URL,
    }
    return render(request, 'tickets/ticket.html', context)


@login_required
def editar_ticket(request, key):
    if is_assinante(request.user):
        if request.method not in ('GET', 'HEAD', 'POST'):
            raise PermissionDenied('Método não permitido para editar o ticket.')
        with transaction.atomic():
            tickets = Ticket.objects.filter(usuario=request.user)
            if request.method == 'POST':
                tickets = tickets.select_for_update()
            ticket = get_object_or_404(tickets, key=key)
            if ticket.status != 'L':
                raise PermissionDenied('O ticket só pode ser editado enquanto estiver em Levantamento.')
            original = {'ticket': ticket.ticket, 'descricao': ticket.descricao}
            form = AssinanteTicketForm(
                request.POST if request.method == 'POST' else None,
                instance=ticket,
            )
            if request.method == 'POST' and form.is_valid():
                changed_fields = [
                    name for name, value in original.items()
                    if form.cleaned_data[name] != value
                ]
                try:
                    if changed_fields:
                        # Salva apenas o que o assinante pode alterar, mantendo o status.
                        with transaction.atomic():
                            ticket.save(update_fields=changed_fields)
                            HistoricoTicket.objects.create(
                                ticket_historico=ticket,
                                descricao_historico='Dados da solicitação atualizados pelo assinante.',
                            )
                        messages.success(request, 'Ticket atualizado com sucesso!')
                    else:
                        messages.info(request, 'Nenhuma alteração foi detectada.')
                except ValidationError as error:
                    form.add_error('ticket', error)
                except IntegrityError:
                    form.add_error('ticket', 'Não foi possível salvar este código. Informe um número único.')
                else:
                    return redirect('exibir-ticket', key=ticket.key)
            return render(request, 'tickets/editar-ticket.html', {
                'form': form,
                'ticket': ticket,
            })
    ticket = ticket_de_operacao(request, key=key)

    form = TicketForm(request.POST or None, instance=ticket, user=request.user)

    if form.is_valid():
        try:
            # Verifica se os dados do formulário foram alterados
            if form.has_changed():
                ticket = form.save(commit=False)
                changed_fields = list(form.changed_data)
                if not str(ticket.ticket or '').strip():
                    changed_fields.append('ticket')
                ticket.save(update_fields=changed_fields)
                messages.success(request, "O Ticket atualizado com sucesso!")
            else:
                messages.info(request, "Nenhuma alteração foi detectada.")
        except ValidationError as error:
            form.add_error('ticket', error)
        except IntegrityError:
            form.add_error('ticket', 'Não foi possível salvar este código. Informe um número único.')
        else:
            return redirect('index-tickets')

    context = {
        'form': form,
        'ticket': ticket,
    }

    return render(request, 'tickets/editar-ticket.html', context)

@login_required
def selecionar_ticket(request):
    tickets = tickets_da_empresa(request.user)
    return render(request, 'index.html', {'tickets': tickets})

@login_required
def buscar_tickets(request):
    if is_assinante(request.user):
        tickets = Ticket.objects.filter(usuario=request.user).order_by('-data_criacao')
        term = request.GET.get('q', request.GET.get('term', '')).strip()
        if term:
            tickets = tickets.filter(ticket__icontains=term)
        return render(request, 'tickets/index-tickets.html', {'tickets': tickets})
    exigir_empresa(request.user)
    tickets = list(tickets_da_empresa(request.user).values('id', 'ticket'))
    return render(request, 'index.html', {
        'tickets_json': json.dumps(tickets)  # <- agora é JSON válido
    })

@login_required
@require_POST
def deletar_ticket(request, key):
    if not pode_gerenciar_empresa(request.user):
        raise PermissionDenied('Somente gerentes podem excluir tickets da empresa.')
    ticket = ticket_de_operacao(request, key=key)

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
@require_POST
def deletar_itemorcamento(request, id, key):
    ticket = ticket_de_financeiro(request, key=key)
    try:
        with transaction.atomic():
            itemorcamento = get_object_or_404(
                ItemOrcamento, id=id, orcamento__ticket_orcamento=ticket,
            )
            orcamento = get_object_or_404(
                Orcamento.objects.select_for_update(),
                pk=itemorcamento.orcamento_id, ticket_orcamento=ticket,
            )
            itemorcamento.delete()
            _salvar_total_orcamento(orcamento)
            messages.success(request, f"Item #{itemorcamento.item} deletado com sucesso.")
    except ProtectedError:
        messages.error(request, "Não foi possível deletar o ticket porque há objetos relacionados protegendo-o.")
    return redirect('exibir-ticket', key)

@login_required
def update_historico(request, key):
    STATUS_DICT = dict(Ticket.STATUS_CHOICES)
    ticket = ticket_de_operacao(request, key=key)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status not in STATUS_DICT:
            # lidar com erro (ex.: reexibir com mensagem)
            return redirect('exibir-ticket', key)

        with transaction.atomic():
            ticket = get_object_or_404(tickets_da_empresa(request.user).select_for_update(), key=key)
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
@require_POST
def deletar_pagamento(request, id, key):
    ticket = ticket_de_financeiro(request, key=key)
    pagamento = get_object_or_404(Pagamentos, id=id, ticket_pagamento=ticket)

    try:
        pagamento.delete()
        messages.success(request, f"Pagamento deletado com sucesso.")
    except ProtectedError:
        messages.error(request, "Não foi possível deletar o pagamento porque há objetos relacionados protegendo-o.")
    return redirect('exibir-ticket', key)

@login_required
def addTicketColaborador(request, id_ticket):
    ticket = ticket_de_operacao(request, pk=id_ticket)
    colaboradores = Colaborador.objects.filter(empresa=ticket.empresa)
    return render(request, 'tickets/add-colaborador-ticket.html', {
        'colaboradores': colaboradores, 'id_ticket': ticket.pk, 'ticket': ticket,
        'title': 'Adicionar Colaborador ao Ticket', 'origem': request.GET.get('origem'),
    })


@login_required
@require_POST
def cadastrarColaboradorTicket(request, id_ticket, id_colaborador):
    ticket = ticket_de_operacao(request, pk=id_ticket)
    ticket.colaborador = get_object_or_404(Colaborador, pk=id_colaborador, empresa=ticket.empresa)
    ticket.save(update_fields=['colaborador'])
    messages.success(request, 'Colaborador adicionado ao ticket com sucesso!')
    return redirect('exibir-ticket', key=ticket.key)


@login_required
def addTicketCliente(request, id_ticket):
    ticket = ticket_de_operacao(request, pk=id_ticket)
    clientes = Cliente.objects.filter(empresa=ticket.empresa)
    return render(request, 'tickets/add-cliente-ticket.html', {
        'clientes': clientes, 'id_ticket': ticket.pk, 'ticket': ticket,
    })


@login_required
@require_POST
def cadastrarTicketCliente(request, id_cliente, id_ticket):
    ticket = ticket_de_operacao(request, pk=id_ticket)
    ticket.cliente = get_object_or_404(Cliente, pk=id_cliente, empresa=ticket.empresa)
    ticket.save(update_fields=['cliente'])
    messages.success(request, 'Cliente adicionado ao ticket com sucesso!')
    return redirect('exibir-ticket', key=ticket.key)


@login_required
def editar_pagamento(request, pagamento_id, key):
    ticket = ticket_de_financeiro(request, key=key)
    pagamento = get_object_or_404(Pagamentos, id=pagamento_id, ticket_pagamento=ticket)

    if request.method == 'POST':
        form = PagamentoForm(request.POST, instance=pagamento)
        if form.is_valid():
            pagamento.data_update_pagamento = timezone.now()
            form.save()
            messages.success(request, "Pagamento atualizado com sucesso!")
            return redirect(f"{reverse('exibir-ticket', kwargs={'key': ticket.key})}#pagamentos")
        # Se o formulário for inválido, vai continuar para renderizar o template com erros
    else:
        form = PagamentoForm(instance=pagamento)

    return render(request, 'tickets/editar-pagamento.html', {
        'form': form,
        'pagamento': pagamento,
        'ticket': ticket
    })

@login_required
def add_pagamento(request, key):
    ticket = ticket_de_financeiro(request, key=key)
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
    return render(request, 'tickets/editar-pagamento.html', {
        'form': form, 'ticket': ticket,
    })


@login_required
@require_POST
def upload_nfe(request, key):
    ticket = ticket_de_financeiro(request, key=key)
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
@require_POST
def delete_nfe(request, key):
    ticket = ticket_de_financeiro(request, key=key)
    
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
    ticket = ticket_de_financeiro(request, key=key)
    pagamento = get_object_or_404(Pagamentos, id=id, ticket_pagamento=ticket)
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
@require_POST
def delete_comprovante(request, id, key):
    ticket = ticket_de_financeiro(request, key=key)
    pagamento = get_object_or_404(Pagamentos, id=id, ticket_pagamento=ticket)

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

@login_required
def gerar_pdf_orcamento(request, ticket_id):
    ticket = ticket_de_financeiro(request, pk=ticket_id)
    try:
        # Pega a primeira empresa cadastrada
        empresa = ticket.empresa
        if not empresa:
            empresa_dict = {
                'nome': 'Sua Empresa',
                'endereco': 'Endereço da Empresa',
                'telefone': '(00) 0000-0000',
                'email': 'contato@empresa.com',
                'cnpj': '00.000.000/0001-00'
            }
        else:
            empresa_dict = {
                'nome': empresa.nome_fantasia,
                'endereco': getattr(empresa, 'endereco', ''),
                'telefone': getattr(empresa, 'telefone', ''),
                'email': getattr(empresa, 'email', ''),
                'cnpj': getattr(empresa, 'cnpj', '')
            }

        orcamento = get_object_or_404(Orcamento.objects.filter(ticket_orcamento=ticket).order_by("pk"))
        itens_orcamento = ItemOrcamento.objects.filter(orcamento=orcamento)

        # Calcular subtotal para cada item e total geral
        total_itens = 0
        for item in itens_orcamento:
            item.subtotal_calculado = item.quant * item.item.valor_unit
            total_itens += item.subtotal_calculado

        # Converter total para Decimal e gerar texto por extenso em reais e centavos
        total_itens = Decimal(total_itens).quantize(Decimal('0.01'))
        reais = int(total_itens)
        centavos = int((total_itens - reais) * 100)

        if centavos > 0:
            texto_por_extenso = f"{num2words(reais, lang='pt-br').capitalize()} reais e {num2words(centavos, lang='pt-br')} centavos"
        else:
            texto_por_extenso = f"{num2words(reais, lang='pt-br').capitalize()} reais"

        context = {
            'empresa': empresa_dict,
            'ticket': ticket,
            'orcamento': orcamento,
            'itens_orcamento': itens_orcamento,
            'total_itens': total_itens,
            'data_emissao': datetime.now().strftime("%d/%m/%Y %H:%M"),
            'logo_path': 'img/logo-mediata-5.1.png',
            'has_logo': True,
            'MEDIA_URL': settings.MEDIA_URL,
            'texto_por_extenso': texto_por_extenso,
            'user': request.user,
        }

        template_path = 'tickets/orcamento_pdf.html'
        template = get_template(template_path)
        html = template.render(context)

        # Gerar PDF com WeasyPrint
        pdf_file = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf()

        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="orcamento_{ticket.ticket}.pdf"'

        return response

    except Ticket.DoesNotExist:
        return HttpResponse('Ticket não encontrado')
    except Orcamento.DoesNotExist:
        return HttpResponse('Orçamento não encontrado para este ticket')

@login_required
@require_POST
def deletar_anexo(request, anexo_id, key):
    ticket = ticket_de_financeiro(request, key=key)
    anexo = get_object_or_404(Anexo, id=anexo_id, ticket_anexo=ticket)
    if request.method == 'POST':
        anexo.delete()
        messages.success(request, 'Anexo removido com sucesso.')
    else:
        messages.error(request, 'Método inválido para deletar anexo.')
    return redirect('exibir-ticket', key=key)

@login_required
@require_http_methods(['GET', 'POST'])
def editar_recebimento(request, recebimento_id, key):
    ticket = ticket_de_financeiro(request, key=key)
    recebimento = get_object_or_404(
        Recebimentos, pk=recebimento_id, ticket_recebimento=ticket,
    )
    form = EditarRecebimentoForm(
        request.POST if request.method == 'POST' else None,
        instance=recebimento,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Recebimento atualizado com sucesso!')
        return redirect(f"{reverse('exibir-ticket', kwargs={'key': ticket.key})}#recebimentos")
    return render(request, 'tickets/editar-recebimento.html', {
        'form': form,
        'recebimento': recebimento,
        'ticket': ticket,
    })


@login_required
@require_POST
def deletar_recebimento(request, recebimento_id, key):
    ticket = ticket_de_financeiro(request, key=key)
    recebimento = get_object_or_404(Recebimentos, id=recebimento_id, ticket_recebimento=ticket)
    if request.method == 'POST':
        recebimento.delete()
        messages.success(request, 'Recebimento removido com sucesso.')
    return redirect('exibir-ticket', key=key)


@login_required
def gerar_pdf_ticket(request, key):
    from django.utils.text import slugify
    from .reports import ticket_report
    from pathlib import Path
    import base64

    ticket = ticket_de_financeiro(request, key=key)
    context = ticket_report(ticket)
    context['company'] = ticket.empresa
    context['generated_by'] = request.user.get_full_name() or request.user.username
    logo_path = Path(settings.BASE_DIR) / 'tickets' / 'assets' / 'logo-mediata.png'
    context['logo_data_uri'] = (
        'data:image/png;base64,' + base64.b64encode(Path(logo_path).read_bytes()).decode('ascii')
        if logo_path.is_file() else None
    )
    responsible = ticket.assumido_por
    if responsible is None and ticket.usuario and not is_assinante(ticket.usuario):
        responsible = ticket.usuario
    context['operation_responsible'] = (
        responsible.get_full_name() or responsible.username if responsible else ''
    )
    html = get_template('tickets/ticket_pdf.html').render(context)
    # A logo é incorporada ao documento, sem requisições HTTP externas.
    pdf = HTML(string=html).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    filename = slugify(ticket.ticket) or str(ticket.key)
    response['Content-Disposition'] = f'attachment; filename="ticket_{filename}_completo.pdf"'
    response['Cache-Control'] = 'private, no-store'
    return response
