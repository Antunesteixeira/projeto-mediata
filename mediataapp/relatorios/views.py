from django.shortcuts import render, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from datetime import timedelta
from decimal import Decimal
from django.db.models import Sum, Q, Prefetch
from tickets.models import Ticket, Orcamento, Pagamentos, Recebimentos
from clientes.models import Cliente
from colaborador.models import Colaborador  
from django.contrib.auth.models import User
from django.core.exceptions import FieldError
from django.db.models import Exists, OuterRef
from django.core.paginator import Paginator


PENDING_TICKET_STATUSES = ('V', 'X', 'E', 'A')


@login_required
def relatorio_view(request):
    # Valores padrão para filtros
    filtros = {
        'date_range': '30',
        'status': 'T', 
        'categoria': 'all',
        'usuario': 'all',
        'cliente': 'all',
        'colaborador': 'all',
        'pagamentos': 'A',  # Tipo de pagamento (Material, Serviço, etc.)
        'status_pagamento': [],  # Status do pagamento (Pendente/Pago) - múltipla seleção
        'data_inicio': '',
        'data_fim': '',
        'status_recebimento': [],  # Status do recebimento (A receber/Recebido) - múltipla seleção
        
    }
    
    # Obtém filtros do formulário
    source = request.POST if request.method == "POST" else request.GET
    for key in filtros.keys():
        # Campos que podem ter múltiplos valores (checkboxes)
        if key in ['status', 'status_pagamento', 'status_recebimento']:
            if key in source and source.getlist(key):
                filtros[key] = source.getlist(key)
            else:
                # Se não vier na requisição, mantém o valor padrão (lista vazia ou string)
                filtros[key] = filtros[key]
        else:
            # Campos de valor único
            filtros[key] = source.get(key, filtros[key])
    
    # Define data limite baseada no date_range ou datas personalizadas
    if filtros['date_range'] == 'custom' and filtros['data_inicio'] and filtros['data_fim']:
        # Usa datas personalizadas
        data_inicio = filtros['data_inicio']
        data_fim = filtros['data_fim']
    else:
        # Usa o período padrão
        try:
            dias = int(filtros['date_range'])
            data_limite = now() - timedelta(days=dias)
        except (ValueError, TypeError):
            data_limite = now() - timedelta(days=30)
    
    # Define escopo base baseado na permissão do usuário
    is_gerente = request.user.groups.filter(name='gerente').exists()
    
    # Query base para Tickets com prefetch de orçamentos e pagamentos
    if is_gerente:
        tickets = Ticket.objects.all()
    else:
        tickets = Ticket.objects.filter(usuario=request.user)
    
    tickets = tickets.prefetch_related(
        Prefetch("orcamento_set", queryset=Orcamento.objects.all(), to_attr="orcamentos_prefetch"),
        Prefetch("recebimentos", queryset=Recebimentos.objects.all(), to_attr="recebimentos_prefetch"),  # <-- adicione esta linha
    )

    # Query base para Orçamentos (para métricas gerais)
    if is_gerente:
        orcamentos = Orcamento.objects.all()
    else:
        orcamentos = Orcamento.objects.filter(ticket_orcamento__usuario=request.user)
    
    # Query base para Pagamentos (para métricas gerais)
    if is_gerente:
        pagamentos = Pagamentos.objects.all()
    else:
        pagamentos = Pagamentos.objects.filter(ticket_pagamento__usuario=request.user)
    
    # Query base para Clientes
    if is_gerente:
        clientes = Cliente.objects.all()
    else:
        clientes = Cliente.objects.filter(ticket__usuario=request.user)
    
    # Aplica filtros comuns a todos os modelos
    
    # Filtro de data
    if filtros['date_range'] == 'custom' and filtros['data_inicio'] and filtros['data_fim']:
        # Filtro por datas personalizadas
        tickets = tickets.filter(data_criacao__range=[filtros['data_inicio'], filtros['data_fim']])
        orcamentos = orcamentos.filter(data_criacao__range=[filtros['data_inicio'], filtros['data_fim']])
    else:
        # Filtro por período padrão
        tickets = tickets.filter(data_criacao__gte=data_limite)
        orcamentos = orcamentos.filter(data_criacao__gte=data_limite)
    
    # Filtro de status do ticket - agora suporta múltiplos valores
    if isinstance(filtros['status'], list):
        # Lista de status (múltipla seleção)
        if 'T' not in filtros['status'] and filtros['status']:  # Se não inclui "Todos" e há status selecionados
            tickets = tickets.filter(status__in=filtros['status'])
            orcamentos = orcamentos.filter(ticket_orcamento__status__in=filtros['status'])
            pagamentos = pagamentos.filter(ticket_pagamento__status__in=filtros['status'])
    else:
        # Status único (compatibilidade com versão anterior)
        if filtros['status'] != "T":
            tickets = tickets.filter(status=filtros['status'])
            orcamentos = orcamentos.filter(ticket_orcamento__status=filtros['status'])
            pagamentos = pagamentos.filter(ticket_pagamento__status=filtros['status'])
    
    # Filtro de usuário (apenas para gerentes)
    if filtros['usuario'] != "all" and is_gerente:
        tickets = tickets.filter(usuario_id=filtros['usuario'])
        orcamentos = orcamentos.filter(ticket_orcamento__usuario_id=filtros['usuario'])
        pagamentos = pagamentos.filter(ticket_pagamento__usuario_id=filtros['usuario'])
        clientes = clientes.filter(ticket__usuario_id=filtros['usuario'])
    
    # Filtro de categoria
    if filtros['categoria'] != "all":
        tickets = tickets.filter(categoria=filtros['categoria'])
        orcamentos = orcamentos.filter(ticket_orcamento__categoria=filtros['categoria'])
        pagamentos = pagamentos.filter(ticket_pagamento__categoria=filtros['categoria'])
    
    # Filtro de cliente
    if filtros['cliente'] != "all":
        tickets = tickets.filter(cliente_id=filtros['cliente'])
        orcamentos = orcamentos.filter(ticket_orcamento__cliente_id=filtros['cliente'])
        pagamentos = pagamentos.filter(ticket_pagamento__cliente_id=filtros['cliente'])
    
    # Filtro de colaborador
    if filtros['colaborador'] != "all":
        tickets = tickets.filter(colaborador_id=filtros['colaborador'])
        orcamentos = orcamentos.filter(ticket_orcamento__colaborador_id=filtros['colaborador'])
        pagamentos = pagamentos.filter(ticket_pagamento__colaborador_id=filtros['colaborador'])
    
    # Filtro por TIPO de pagamento (Material, Serviço, etc.)
    if filtros['pagamentos'] != "A":
        # Filtra os querysets de pagamentos e orçamentos
        pagamentos = pagamentos.filter(tipo=filtros['pagamentos'])
        # Nota: orçamentos não têm tipo de pagamento, então não filtramos
    
    # Filtro por STATUS de pagamento (Pendente/Pago) - múltipla seleção
    if filtros['status_pagamento'] and len(filtros['status_pagamento']) > 0:
        # Converte strings 'True'/'False' para booleanos, se necessário
        status_boolean = []
        for val in filtros['status_pagamento']:
            if val == 'True':
                status_boolean.append(True)
            elif val == 'False':
                status_boolean.append(False)
            else:
                status_boolean.append(val)  # caso venha como booleano nativo
        
        # Filtra os pagamentos pelos status selecionados
        pagamentos = pagamentos.filter(status_pagamento__in=status_boolean)

        # Quando Pendente é selecionado, só os quatro estágios operacionais são elegíveis.
        if False in status_boolean:
            tickets = tickets.filter(status__in=PENDING_TICKET_STATUSES)
            pagamentos = pagamentos.filter(ticket_pagamento__status__in=PENDING_TICKET_STATUSES)

    # Tipo e status precisam corresponder ao mesmo registro de pagamento.
    if filtros['pagamentos'] != 'A' or filtros['status_pagamento']:
        tickets = tickets.filter(Exists(pagamentos.filter(ticket_pagamento_id=OuterRef('pk'))))
    
    # Filtro por STATUS de recebimento (A receber/Recebido) - múltipla seleção
    if filtros['status_recebimento']:
        status_recebimento_boolean = []
        for val in filtros['status_recebimento']:
            if val in ('True', 'true', '1'):
                status_recebimento_boolean.append(True)
            elif val in ('False', 'false', '0'):
                status_recebimento_boolean.append(False)
            else:
                # Caso o valor já venha como booleano nativo
                status_recebimento_boolean.append(val)

        # Aplica o filtro nos tickets (ajuste o related_name e o campo)
        tickets = tickets.filter(
            recebimentos__status_recebimento__in=status_recebimento_boolean
        ).distinct()

    # A janela de datas continua sendo a de criação dos tickets. Os pagamentos
    # usados nos totais e na coluna respeitam os filtros de tipo/status aplicados.
    tickets = tickets.prefetch_related(
        Prefetch('pagamentos', queryset=pagamentos, to_attr='pagamentos_prefetch'),
    )
    tickets_list = list(tickets)
    total_pagos = Decimal('0')
    total_pendentes = Decimal('0')
    
    for ticket in tickets_list:
        # Soma dos orçamentos
        ticket.total_orcamentos = sum(o.valor_total for o in getattr(ticket, "orcamentos_prefetch", []))

        # Distribui somente os pagamentos que passaram pelos filtros do relatório.
        ticket.pagamentos_por_tipo = {tipo: Decimal('0') for tipo, _ in Pagamentos.TIPO_CHOICES}
        ticket.total_pagamentos = Decimal('0')
        for pagamento in getattr(ticket, "pagamentos_prefetch", []):
            valor = pagamento.valor_pagamento or Decimal('0')
            ticket.total_pagamentos += valor
            ticket.pagamentos_por_tipo[pagamento.tipo] = (
                ticket.pagamentos_por_tipo.get(pagamento.tipo, Decimal('0')) + valor
            )
            if pagamento.status_pagamento:
                total_pagos += valor
            else:
                total_pendentes += valor

    # Calcula métricas gerais
    try:
        orcamento_total = sum([ticket.total_orcamentos for ticket in tickets_list])
    except:
        orcamento_total = 0
    
    try:
        total_pagamentos = sum([ticket.total_pagamentos for ticket in tickets_list])
    except:
        total_pagamentos = 0
    
    # Calcula ticket médio e lucro
    ticket_count = len(tickets_list)
    ticket_medio = orcamento_total / ticket_count if ticket_count > 0 else 0
    total_lucros = orcamento_total - total_pagamentos
    
    # Novos clientes no período
    if filtros['date_range'] == 'custom' and filtros['data_inicio'] and filtros['data_fim']:
        novos_clientes = clientes.filter(data_cadastro__range=[filtros['data_inicio'], filtros['data_fim']]).count()
    else:
        novos_clientes = clientes.filter(data_cadastro__gte=data_limite).count()
    
    # Lista de usuários para filtro (apenas para gerentes)
    usuarios = User.objects.all() if is_gerente else User.objects.filter(id=request.user.id)
    
    # Lista de colaboradores para filtro - Versão mais eficiente
    if is_gerente:
        # Gerente: todos os colaboradores que aparecem em qualquer ticket
        colaboradores = Colaborador.objects.filter(
            Exists(Ticket.objects.filter(colaborador=OuterRef('pk')))
        ).distinct()
    else:
        # Usuário normal: colaboradores que aparecem nos SEUS tickets
        colaboradores = Colaborador.objects.filter(
            Exists(Ticket.objects.filter(colaborador=OuterRef('pk'), usuario=request.user))
        ).distinct()

    # Lista de clientes para filtro - COM DISTINCT
    if is_gerente:
        # Gerente vê todos os clientes distintos que têm tickets
        clientes_list = Cliente.objects.filter(
            ticket__isnull=False
        ).distinct().order_by('nome_razao_social')
    else:
        # Usuário normal vê clientes distintos dos SEUS tickets
        clientes_list = Cliente.objects.filter(
            ticket__usuario=request.user
        ).distinct().order_by('nome_razao_social')

    # Prepara contexto
    context = {
        "tickets": tickets,
        "clientes": clientes_list,
        "orcamento_total": orcamento_total,
        "ticket_medio": ticket_medio,
        "total_pagamentos": total_pagamentos,
        "total_lucros": total_lucros,
        "novos_clientes": novos_clientes,
        "colaboradores": colaboradores,
        "usuarios": usuarios,
        "filtro_date_range": filtros['date_range'],
        "filtro_status": filtros['status'] if isinstance(filtros['status'], str) else 'T',
        "filtro_status_list": filtros['status'] if isinstance(filtros['status'], list) else [filtros['status']],
        "filtro_categoria": filtros['categoria'],
        "filtro_usuario": filtros['usuario'],
        "filtro_cliente": filtros['cliente'],
        "filtro_colaborador": filtros['colaborador'],
        "filtro_pagamentos": filtros['pagamentos'],  # Tipo de pagamento selecionado
        "filtro_status_pagamento_list": filtros['status_pagamento'],  # Lista de status de pagamento selecionados
        "filtro_data_inicio": filtros['data_inicio'],
        "filtro_data_fim": filtros['data_fim'],
        "filtro_status_recebimento": filtros['status_recebimento'],
        "is_gerente": is_gerente,
        "eh_lucro": total_lucros >= 0,
        "percentual_lucro": (total_lucros / orcamento_total * 100) if orcamento_total > 0 else 0,
        # NOVOS CAMPOS
        "total_pagos": total_pagos,
        "total_pendentes": total_pendentes,
    }
    
    return render(request, "relatorios/index-relatorios.html", context)