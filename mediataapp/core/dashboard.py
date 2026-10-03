"""Dados do painel calculados apenas a partir dos tickets autorizados."""

from collections import Counter
from decimal import Decimal

from django.db.models import Prefetch
from django.utils import timezone

from tickets.models import Orcamento, Pagamentos, Recebimentos, Ticket


ZERO = Decimal("0.00")
MONTH_NAMES = (
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
)
STATUS_COLORS = {
    "L": "#64748b",
    "C": "#a78bfa",
    "A": "#3b82f6",
    "E": "#f59e0b",
    "X": "#14b8a6",
    "V": "#06b6d4",
    "F": "#10b981",
    "R": "#ef4444",
}
HISTOGRAM_RANGES = (
    ("Até R$ 1 mil", Decimal("1000")),
    ("R$ 1–5 mil", Decimal("5000")),
    ("R$ 5–10 mil", Decimal("10000")),
    ("R$ 10–25 mil", Decimal("25000")),
    ("Acima de R$ 25 mil", None),
)


def _month_keys(now):
    """Inclui o mês atual e os cinco anteriores, em ordem cronológica."""
    current = now.year * 12 + now.month - 1
    return [divmod(index, 12) for index in range(current - 5, current + 1)]


def _local_month(value):
    local = timezone.localtime(value)
    return local.year, local.month - 1


def _ranking(counts, labels):
    ordered = sorted(counts, key=lambda key: (-counts[key], labels[key].casefold(), key))
    return [{"label": labels[key], "value": counts[key]} for key in ordered[:5]]


def build_dashboard_context(tickets, company, can_view_all, now=None):
    """Monta indicadores, gráficos e tabela sem consultas por ticket.

    O chamador deve fornecer um queryset já limitado ao escopo do usuário.
    Somas de orçamentos, pagamentos e recebimentos são independentes para
    evitar multiplicação de valores quando um ticket tem várias relações.
    """
    now = timezone.localtime(now or timezone.now())
    tickets = list(tickets.select_related("usuario", "cliente", "colaborador").prefetch_related(
        Prefetch("orcamento_set", queryset=Orcamento.objects.all(), to_attr="orcamentos_prefetch"),
        Prefetch("pagamentos", queryset=Pagamentos.objects.all(), to_attr="pagamentos_prefetch"),
        Prefetch("recebimentos", queryset=Recebimentos.objects.all(), to_attr="recebimentos_prefetch"),
    ))

    metrics = {
        "tickets_total": len(tickets),
        "active": 0,
        "finalized": 0,
        "emergency": 0,
        "budget_total": ZERO,
        "budget_month": ZERO,
        "paid_total": ZERO,
        "pending_payments": ZERO,
        "receivable_total": ZERO,
        "received_total": ZERO,
        "operators_count": 0,
        "clients_count": 0,
        "collaborators_count": 0,
    }
    status_counts = Counter()
    monthly = {
        key: {"label": f"{MONTH_NAMES[key[1]]}/{key[0]}", "tickets": 0, "budget": ZERO}
        for key in _month_keys(now)
    }
    current_month = (now.year, now.month - 1)
    histogram = [{"label": label, "value": 0} for label, _ in HISTOGRAM_RANGES]
    counts = {"operators": Counter(), "clients": Counter(), "collaborators": Counter()}
    labels = {key: {} for key in counts}
    month_budgets = []

    for ticket in tickets:
        status_counts[ticket.status] += 1
        metrics["active"] += ticket.status not in ("F", "R")
        metrics["finalized"] += ticket.status == "F"
        metrics["emergency"] += ticket.emergencial

        ticket_month = _local_month(ticket.data_criacao)
        if ticket_month in monthly:
            monthly[ticket_month]["tickets"] += 1

        ticket.total_orcamentos = sum(
            (budget.valor_total or ZERO for budget in ticket.orcamentos_prefetch), ZERO,
        )
        ticket.total_pagamentos = sum(
            (payment.valor_pagamento or ZERO for payment in ticket.pagamentos_prefetch), ZERO,
        )
        metrics["budget_total"] += ticket.total_orcamentos

        for budget in ticket.orcamentos_prefetch:
            value = budget.valor_total or ZERO
            budget_month = _local_month(budget.data_criacao)
            if budget_month in monthly:
                monthly[budget_month]["budget"] += value
            if budget_month == current_month:
                metrics["budget_month"] += value
                month_budgets.append(budget)

        for payment in ticket.pagamentos_prefetch:
            key = "paid_total" if payment.status_pagamento else "pending_payments"
            metrics[key] += payment.valor_pagamento or ZERO

        for receipt in ticket.recebimentos_prefetch:
            key = "received_total" if receipt.status_recebimento else "receivable_total"
            metrics[key] += receipt.valor_recebimento or ZERO

        if ticket.total_orcamentos > ZERO:
            for index, (_, limit) in enumerate(HISTOGRAM_RANGES):
                if limit is None or ticket.total_orcamentos <= limit:
                    histogram[index]["value"] += 1
                    break

        if ticket.usuario_id is not None:
            counts["operators"][ticket.usuario_id] += 1
            labels["operators"][ticket.usuario_id] = (
                ticket.usuario.get_full_name().strip() or ticket.usuario.username
            )
        if ticket.cliente_id is not None:
            counts["clients"][ticket.cliente_id] += 1
            labels["clients"][ticket.cliente_id] = str(ticket.cliente)
        if ticket.colaborador_id is not None:
            counts["collaborators"][ticket.colaborador_id] += 1
            labels["collaborators"][ticket.colaborador_id] = str(ticket.colaborador)

    metrics["operators_count"] = len(counts["operators"])
    metrics["clients_count"] = len(counts["clients"])
    metrics["collaborators_count"] = len(counts["collaborators"])
    charts = {
        "status": [
            {"key": key, "label": label, "value": status_counts[key], "color": STATUS_COLORS[key]}
            for key, label in Ticket.STATUS_CHOICES
        ],
        "monthly": [
            {**values, "budget": float(values["budget"])}
            for values in monthly.values()
        ],
        "histogram": histogram,
        **{key: _ranking(counts[key], labels[key]) for key in counts},
    }

    return {
        "tickets": tickets,
        "tickets_total": metrics["tickets_total"],
        "orcamentos": month_budgets,
        "total_mes": metrics["budget_month"],
        "dashboard_metrics": metrics,
        "dashboard_charts": charts,
        "dashboard_company": company,
        "dashboard_scope": "Visão da empresa" if can_view_all else "Seus tickets",
        "dashboard_updated_at": now,
        "dashboard_can_view_all": can_view_all,
    }
