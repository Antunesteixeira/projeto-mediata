"""Dados do relatório completo, sem alterar o ticket durante a exportação."""
from datetime import date, datetime
from decimal import Decimal

from django.db import models
from django.utils import formats, timezone

from .models import Orcamento, Pagamentos


LABELS = {
    'usuario': 'Responsável pelo ticket', 'descricao': 'Descrição',
    'valor_mao_obra': 'Valor de mão de obra', 'valor_custo': 'Valor de custo',
    'valor_faturamento': 'Valor de faturamento', 'valor_equipamento': 'Valor de equipamento',
    'data_criacao': 'Data de criação', 'ultimo_update': 'Última atualização',
    'data_finalizar': 'Data de finalização', 'nfe_path': 'Arquivo da nota fiscal',
    'orcamento': 'Orçamento', 'descricao_historico': 'Descrição do histórico',
    'data_historico': 'Data do histórico', 'data_update_pagamento': 'Data de registro do pagamento',
    'razao_social': 'Razão social', 'numero_nota_fiscal': 'Número da nota fiscal',
    'serie_nota_fiscal': 'Série da nota fiscal', 'data_emissao': 'Data de emissão',
    'descricao_recebimento': 'Descrição do recebimento', 'descricao_anexo': 'Descrição do anexo',
}


def money(value):
    return 'R$ ' + formats.number_format(value or Decimal('0'), 2, use_l10n=True, force_grouping=True)


def information(instance, exclude=(), include=None, overrides=None):
    if instance is None:
        return []
    rows = []
    for field in instance._meta.fields:
        if field.primary_key or field.name in ('key', *exclude):
            continue
        if include is not None and field.name not in include:
            continue
        value = overrides[field.name] if overrides and field.name in overrides else getattr(instance, field.name)
        if value is None or value == '':
            value = 'Não informado'
        elif field.choices:
            value = getattr(instance, f'get_{field.name}_display')()
        elif isinstance(value, bool):
            value = 'Sim' if value else 'Não'
        elif isinstance(value, datetime):
            value = formats.date_format(timezone.localtime(value), 'd/m/Y H:i')
        elif isinstance(value, date):
            value = formats.date_format(value, 'd/m/Y')
        elif isinstance(field, models.DecimalField):
            value = money(value) if field.name.startswith('valor') else formats.number_format(value, 2)
        else:
            value = str(value)
        label = LABELS.get(field.name, str(field.verbose_name).replace('_', ' ').capitalize())
        rows.append((label, value))
    return rows


def ticket_report(ticket):
    budgets = []
    total_budget = Decimal('0')
    for budget in Orcamento.objects.filter(ticket_orcamento=ticket).order_by('data_criacao', 'pk'):
        items = []
        total = Decimal('0')
        for entry in budget.itemorcamento_set.select_related('item').order_by('pk'):
            unit_price = entry.item.valor_unit if entry.item and entry.item.valor_unit is not None else Decimal('0')
            subtotal = entry.quant * unit_price
            total += subtotal
            items.append({
                'name': str(entry.item) if entry.item else 'Insumo removido',
                'code': entry.item.codigo if entry.item else '—',
                'type': entry.item.get_tipo_display() if entry.item else '—',
                'unit': entry.item.get_unidade_display() if entry.item else '—',
                'quantity': entry.quant, 'price': money(unit_price), 'subtotal': money(subtotal),
            })
        budgets.append({
            'name': budget.orcamento,
            'fields': information(budget, exclude=('ticket_orcamento',), overrides={'valor_total': total}),
            'items': items, 'total': money(total),
            'materials': [information(obj, exclude=('orcamento_material',)) for obj in budget.material_set.all()],
            'services': [information(obj, exclude=('orcamento_servico',)) for obj in budget.servico_set.all()],
        })
        total_budget += total
    payments = list(ticket.pagamentos.order_by('data_pagamento', 'pk'))
    receipts = list(ticket.recebimentos.order_by('data_recebimento', 'pk'))
    paid = sum((p.valor_pagamento or Decimal('0') for p in payments if p.status_pagamento), Decimal('0'))
    pending = sum((p.valor_pagamento or Decimal('0') for p in payments if not p.status_pagamento), Decimal('0'))
    received = sum((r.valor_recebimento or Decimal('0') for r in receipts if r.status_recebimento), Decimal('0'))
    to_receive = sum((r.valor_recebimento or Decimal('0') for r in receipts if not r.status_recebimento), Decimal('0'))
    costs_by_type = {kind: Decimal('0') for kind, _ in Pagamentos.TIPO_CHOICES}
    for payment in payments:
        costs_by_type[payment.tipo] = costs_by_type.get(payment.tipo, Decimal('0')) + (payment.valor_pagamento or Decimal('0'))
    financial_values = {
        'valor_material': costs_by_type['M'],
        'valor_mao_obra': costs_by_type['O'],
        'valor_custo': paid + pending,
        'valor_faturamento': total_budget,
        'valor_equipamento': costs_by_type['E'],
    }
    return {
        'ticket': ticket,
        'issued_at': timezone.localtime(),
        'ticket_fields': information(ticket, overrides=financial_values),
        'financial_basis': 'Os valores de material, mão de obra e equipamento incluem pagamentos realizados e pendentes. '
                           'O custo total inclui todas as categorias de pagamento, e o faturamento corresponde ao total dos itens orçados.',
        'client_fields': information(ticket.cliente),
        'collaborator_fields': information(ticket.colaborador, include=(
            'tipo_pessoa', 'nome_completo', 'cpf', 'rg', 'razao_social', 'cnpj',
            'nome_fantasia', 'email', 'telefone', 'endereco', 'ativo',
        )),
        'budgets': budgets,
        'summary': [('Total dos itens orçados', money(total_budget)), ('Pagamentos realizados', money(paid)),
                    ('Pagamentos pendentes', money(pending)), ('Saldo do orçamento após pagamentos', money(total_budget - paid - pending)),
                    ('Recebido', money(received)), ('A receber', money(to_receive))],
        'payments': [information(p, exclude=('ticket_pagamento',)) for p in payments],
        'receipts': [information(r, exclude=('ticket_recebimento',)) for r in receipts],
        'history': [information(h, exclude=('ticket_historico',)) for h in ticket.historicoticket_set.order_by('data_historico', 'pk')],
        'attachments': [information(a, exclude=('ticket_anexo',)) for a in ticket.anexos.order_by('data_upload', 'pk')],
    }
