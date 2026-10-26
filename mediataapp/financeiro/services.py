from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import BooleanField, Case, CharField, Count, DecimalField, F, IntegerField, Q, Sum, UUIDField, Value, When
from django.db.models.functions import Cast, Coalesce, NullIf, TruncDate
from zoneinfo import ZoneInfo

from core.tenancy import dados_da_empresa, pode_acessar_financeiro, tickets_da_empresa
from .models import LancamentoManual
from tickets.models import Pagamentos, Recebimentos


ZERO = Decimal('0.00')
SITUACOES = {
    'pago': 'Pago', 'recebido': 'Recebido', 'vencido': 'Vencido',
    'aberto': 'Em aberto', 'sem_vencimento': 'Sem vencimento',
}
MONEY_KEYS = (
    'credito', 'debito', 'recebido', 'pago', 'a_receber', 'a_pagar',
    'vencido_credito', 'vencido_debito',
)
COUNT_KEYS = (
    'quantidade', 'sem_vencimento_count', 'sem_valor_count',
    'sem_quitacao_count', 'confirmacao_divergente_count',
)
ROW_FIELDS = (
    'origem', 'operacao', 'origem_id', 'ticket_id', 'ticket_codigo', 'ticket_key',
    'empresa_nome', 'descricao', 'contraparte', 'vencimento', 'valor',
    'situacao', 'quitacao', 'sem_valor', 'legado_sem_quitacao',
    'confirmacao_divergente', 'ordem_sem_vencimento',
)


def totais_vazios():
    return {**dict.fromkeys(MONEY_KEYS, ZERO), **dict.fromkeys(COUNT_KEYS, 0)}


def fontes_financeiras(user, filtros, hoje):
    if not pode_acessar_financeiro(user):
        raise PermissionDenied('Seu acesso não permite consultar o financeiro da empresa.')
    tickets = tickets_da_empresa(user)
    pagamentos = Pagamentos.objects.filter(ticket_pagamento__in=tickets)
    recebimentos = Recebimentos.objects.filter(ticket_recebimento__in=tickets)
    operacao, situacao = filtros['operacao'], filtros['situacao']
    if operacao == 'credito':
        pagamentos = pagamentos.none()
    elif operacao == 'debito':
        recebimentos = recebimentos.none()
    if situacao == 'pago':
        pagamentos = pagamentos.filter(status_pagamento=True)
        recebimentos = recebimentos.none()
    elif situacao == 'recebido':
        pagamentos = pagamentos.none()
        recebimentos = recebimentos.filter(status_recebimento=True)
    elif situacao in ('vencido', 'aberto'):
        comparison = 'lt' if situacao == 'vencido' else 'gte'
        vencimento = {f'data_vencimento__{comparison}': hoje}
        pagamentos = pagamentos.filter(status_pagamento=False, **vencimento)
        recebimentos = recebimentos.filter(status_recebimento=False, **vencimento)
    if filtros.get('data_inicio') is not None and filtros.get('data_fim') is not None:
        intervalo = (filtros['data_inicio'], filtros['data_fim'])
        pagamentos = pagamentos.filter(data_vencimento__range=intervalo)
        recebimentos = recebimentos.filter(data_vencimento__range=intervalo)
    manuais = dados_da_empresa(user, LancamentoManual.objects.all())
    if operacao in ('credito', 'debito'):
        manuais = manuais.filter(operacao=operacao)
    if situacao in ('pago', 'recebido'):
        manuais = manuais.filter(
            operacao='debito' if situacao == 'pago' else 'credito', liquidado=True,
        )
    elif situacao in ('vencido', 'aberto'):
        comparison = 'lt' if situacao == 'vencido' else 'gte'
        manuais = manuais.filter(liquidado=False, **{f'data_vencimento__{comparison}': hoje})
    if filtros.get('data_inicio') is not None and filtros.get('data_fim') is not None:
        manuais = manuais.filter(data_vencimento__range=(filtros['data_inicio'], filtros['data_fim']))
    return pagamentos, recebimentos, manuais


def _divergencia(credito):
    if credito:
        return (
            Q(status_recebimento=True, recebimento_realizado=False)
            | Q(status_recebimento=False, recebimento_realizado=True)
            | Q(status_recebimento=False, data_recebimento_realizado__isnull=False)
        )
    return Q(status_pagamento=False, data_pagamento_realizado__isnull=False)


def calcular_totais(pagamentos, recebimentos, hoje, manuais=None):
    totais = totais_vazios()
    for fonte, credito in ((pagamentos, False), (recebimentos, True)):
        campo_valor = 'valor_recebimento' if credito else 'valor_pagamento'
        campo_status = 'status_recebimento' if credito else 'status_pagamento'
        campo_baixa = 'data_recebimento_realizado' if credito else 'data_pagamento_realizado'
        liquidado, pendente = Q(**{campo_status: True}), Q(**{campo_status: False})
        resumo = fonte.aggregate(
            total=Sum(campo_valor, default=ZERO),
            realizado=Sum(campo_valor, filter=liquidado, default=ZERO),
            pendente=Sum(campo_valor, filter=pendente, default=ZERO),
            vencido=Sum(campo_valor, filter=pendente & Q(data_vencimento__lt=hoje), default=ZERO),
            quantidade=Count('pk'),
            sem_vencimento_count=Count('pk', filter=Q(data_vencimento__isnull=True)),
            sem_valor_count=Count('pk', filter=Q(**{f'{campo_valor}__isnull': True})),
            sem_quitacao_count=Count('pk', filter=liquidado & Q(**{f'{campo_baixa}__isnull': True})),
            confirmacao_divergente_count=Count('pk', filter=_divergencia(credito)),
        )
        totais['credito' if credito else 'debito'] = resumo['total']
        totais['recebido' if credito else 'pago'] = resumo['realizado']
        totais['a_receber' if credito else 'a_pagar'] = resumo['pendente']
        totais['vencido_credito' if credito else 'vencido_debito'] = resumo['vencido']
        for key in COUNT_KEYS:
            totais[key] += resumo[key]
    if manuais is not None:
        regras = {
            'credito': Q(operacao='credito'), 'debito': Q(operacao='debito'),
            'recebido': Q(operacao='credito', liquidado=True),
            'pago': Q(operacao='debito', liquidado=True),
            'a_receber': Q(operacao='credito', liquidado=False),
            'a_pagar': Q(operacao='debito', liquidado=False),
            'vencido_credito': Q(operacao='credito', liquidado=False, data_vencimento__lt=hoje),
            'vencido_debito': Q(operacao='debito', liquidado=False, data_vencimento__lt=hoje),
        }
        resumo = manuais.aggregate(
            **{key: Sum('valor', filter=condition, default=ZERO) for key, condition in regras.items()},
            quantidade=Count('pk'),
        )
        for key in MONEY_KEYS:
            totais[key] += resumo[key]
        totais['quantidade'] += resumo['quantidade']
    return totais


def _linhas(fonte, credito, hoje):
    parent = 'ticket_recebimento' if credito else 'ticket_pagamento'
    status = 'status_recebimento' if credito else 'status_pagamento'
    baixa = 'data_recebimento_realizado' if credito else 'data_pagamento_realizado'
    descricao = (
        Coalesce(NullIf('descricao_recebimento', Value('')), Value('Recebimento do ticket'), output_field=CharField())
        if credito else Case(
            *(When(tipo=tipo, then=Value(label)) for tipo, label in Pagamentos.TIPO_CHOICES),
            default=Value('Pagamento do ticket'), output_field=CharField(),
        )
    )
    contraparte = (
        Coalesce(
            NullIf('razao_social', Value('')),
            NullIf(f'{parent}__cliente__nome_razao_social', Value('')),
            Value('Não informado'), output_field=CharField(),
        ) if credito else Value('Não informado', output_field=CharField())
    )
    # O status é a referência da quitação; a data de cadastro nunca é uma baixa.
    quitacao = Case(
        When(**{status: True}, then=(
            TruncDate(baixa, tzinfo=ZoneInfo(settings.TIME_ZONE)) if credito else F(baixa)
        )),
        default=None,
    )
    return fonte.order_by().annotate(
        origem=Value('ticket', output_field=CharField()),
        operacao=Value('credito' if credito else 'debito', output_field=CharField()),
        origem_id=F('pk'), ticket_id=F(f'{parent}_id'),
        ticket_codigo=F(f'{parent}__ticket'), ticket_key=F(f'{parent}__key'),
        empresa_nome=Coalesce(f'{parent}__empresa__nome_fantasia', Value('Sem empresa')),
        descricao=descricao, contraparte=contraparte,
        vencimento=F('data_vencimento'), valor=Cast('valor_recebimento' if credito else 'valor_pagamento', DecimalField(max_digits=12, decimal_places=2)),
        situacao=Case(
            When(**{status: True}, then=Value('recebido' if credito else 'pago')),
            When(data_vencimento__isnull=True, then=Value('sem_vencimento')),
            When(data_vencimento__lt=hoje, then=Value('vencido')),
            default=Value('aberto'), output_field=CharField(),
        ),
        quitacao=quitacao,
        sem_valor=Case(When(**{('valor_recebimento' if credito else 'valor_pagamento') + '__isnull': True}, then=True), default=False, output_field=BooleanField()),
        legado_sem_quitacao=Case(When(Q(**{status: True}) & Q(**{f'{baixa}__isnull': True}), then=True), default=False, output_field=BooleanField()),
        confirmacao_divergente=Case(When(_divergencia(credito), then=True), default=False, output_field=BooleanField()),
        ordem_sem_vencimento=Case(When(data_vencimento__isnull=True, then=1), default=0, output_field=IntegerField()),
    ).values(*ROW_FIELDS)


def _linhas_manuais(manuais, hoje):
    return manuais.order_by().annotate(
        origem=Value('manual', output_field=CharField()), origem_id=F('pk'),
        ticket_id=Value(None, output_field=IntegerField()),
        ticket_codigo=Value(None, output_field=CharField()),
        ticket_key=Value(None, output_field=UUIDField()),
        empresa_nome=F('empresa__nome_fantasia'),
        vencimento=F('data_vencimento'),
        situacao=Case(
            When(operacao='credito', liquidado=True, then=Value('recebido')),
            When(operacao='debito', liquidado=True, then=Value('pago')),
            When(data_vencimento__lt=hoje, then=Value('vencido')),
            default=Value('aberto'), output_field=CharField(),
        ),
        quitacao=F('data_quitacao'),
        sem_valor=Value(False, output_field=BooleanField()),
        legado_sem_quitacao=Value(False, output_field=BooleanField()),
        confirmacao_divergente=Value(False, output_field=BooleanField()),
        ordem_sem_vencimento=Value(0, output_field=IntegerField()),
    ).values(*ROW_FIELDS)


def consolidar_lancamentos(pagamentos, recebimentos, hoje, manuais=None):
    fontes = [_linhas(recebimentos, True, hoje)]
    if manuais is not None:
        fontes.append(_linhas_manuais(manuais, hoje))
    return _linhas(pagamentos, False, hoje).union(
        *fontes, all=True,
    ).order_by('ordem_sem_vencimento', 'vencimento', 'operacao', 'origem', 'origem_id')
