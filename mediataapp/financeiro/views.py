from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from core.tenancy import dados_da_empresa, pode_acessar_financeiro, tickets_da_empresa
from tickets.forms import EditarRecebimentoForm, PagamentoForm
from tickets.models import Pagamentos, Recebimentos
from .forms import FiltroFinanceiroForm, LancamentoManualForm
from .models import LancamentoManual
from .services import (
    SITUACOES, calcular_totais, consolidar_lancamentos,
    fontes_financeiras, totais_vazios,
)


def _exigir_acesso(user):
    if not pode_acessar_financeiro(user):
        raise PermissionDenied('Seu acesso não permite consultar o financeiro da empresa.')


def _consulta(params, incluir_pagina=False):
    values = {key: params.get(key) for key in FiltroFinanceiroForm.base_fields if params.get(key)}
    page = params.get('page', '')
    try:
        page_number = int(page) if len(str(page)) <= 10 else 0
    except (ValueError, TypeError):
        page_number = 0
    if incluir_pagina and page_number > 0:
        values['page'] = str(page_number)
    return urlencode(values)


def _render_index(request, *, manual_form=None):
    _exigir_acesso(request.user)
    hoje = timezone.localdate()
    form = FiltroFinanceiroForm(request.GET, hoje=hoje)
    valid = form.is_valid()
    totais, linhas = totais_vazios(), []
    consulta = ''
    if valid:
        form.apresentar_intervalo()
        pagamentos, recebimentos, manuais = fontes_financeiras(request.user, form.cleaned_data, hoje)
        totais = calcular_totais(pagamentos, recebimentos, hoje, manuais=manuais)
        linhas = consolidar_lancamentos(pagamentos, recebimentos, hoje, manuais=manuais)
        consulta = _consulta(form.data)
    page = Paginator(linhas, 25).get_page(request.GET.get('page'))
    consulta_edicao = consulta
    if page.number > 1:
        consulta_edicao += ('&' if consulta_edicao else '') + urlencode({'page': page.number})
    for linha in page.object_list:
        credito = linha['operacao'] == 'credito'
        linha['operacao_label'] = 'Crédito' if credito else 'Débito'
        linha['situacao_label'] = SITUACOES[linha['situacao']]
        rota_edicao = ('financeiro:editar-manual' if linha['origem'] == 'manual' else
                       'financeiro:editar-recebimento' if credito else 'financeiro:editar-pagamento')
        linha['url_edicao'] = reverse(
            rota_edicao,
            kwargs={'pk': linha['origem_id']},
        ) + (f'?{consulta_edicao}' if consulta_edicao else '')
    novo_lancamento_url = reverse('financeiro:novo-lancamento')
    if consulta_edicao:
        novo_lancamento_url += f'?{consulta_edicao}'
    return render(request, 'financeiro/index.html', {
        'form': form, 'page_obj': page, 'lancamentos': page,
        'totais': totais, 'querystring_filtros': consulta,
        'data_hoje': hoje.isoformat(),
        'manual_form': manual_form if manual_form is not None else LancamentoManualForm(
            actor=request.user, auto_id='id_manual_%s',
        ),
        'novo_lancamento_url': novo_lancamento_url,
        'reabrir_novo_lancamento': manual_form is not None,
    }, status=200 if valid else 400)


@login_required
@require_GET
def index(request):
    return _render_index(request)


def _editar(request, pk, credito):
    _exigir_acesso(request.user)
    model = Recebimentos if credito else Pagamentos
    field = 'ticket_recebimento' if credito else 'ticket_pagamento'
    fonte = model.objects.filter(**{f'{field}__in': tickets_da_empresa(request.user)})
    form_class = EditarRecebimentoForm if credito else PagamentoForm
    consulta = _consulta(request.GET, incluir_pagina=True)
    voltar = reverse('financeiro:index') + (f'?{consulta}' if consulta else '')
    with transaction.atomic():
        if request.method == 'POST':
            fonte = fonte.select_for_update()
        registro = get_object_or_404(fonte, pk=pk)
        form = form_class(request.POST if request.method == 'POST' else None, instance=registro)
        if request.method == 'POST' and form.is_valid():
            if not credito:
                registro.data_update_pagamento = timezone.now()
            form.save()
            messages.success(request, 'Lançamento atualizado com sucesso!')
            return redirect(voltar)
    return render(request, 'financeiro/editar-lancamento.html', {
        'form': form, 'registro': registro, 'ticket': getattr(registro, field),
        'titulo': 'Editar recebimento' if credito else 'Editar pagamento', 'voltar_url': voltar,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def editar_pagamento(request, pk):
    return _editar(request, pk, credito=False)


@login_required
@require_http_methods(['GET', 'POST'])
def editar_recebimento(request, pk):
    return _editar(request, pk, credito=True)



def _lancamento_manual(request, pk=None):
    _exigir_acesso(request.user)
    consulta = _consulta(request.GET, incluir_pagina=True)
    voltar = reverse('financeiro:index') + (f'?{consulta}' if consulta else '')
    modal = pk is None and request.POST.get('apresentacao') == 'modal'
    with transaction.atomic():
        registro = None
        if pk is not None:
            fonte = dados_da_empresa(request.user, LancamentoManual.objects.all())
            if request.method == 'POST':
                fonte = fonte.select_for_update()
            registro = get_object_or_404(fonte, pk=pk)
        form = LancamentoManualForm(
            request.POST if request.method == 'POST' else None,
            actor=request.user, instance=registro,
            auto_id='id_manual_%s' if modal else 'id_%s',
        )
        if request.method == 'POST' and form.is_valid():
            lancamento = form.save(commit=False)
            if registro is None:
                lancamento.criado_por = request.user
            lancamento.save()
            messages.success(request, 'Lançamento cadastrado com sucesso!' if registro is None else 'Lançamento atualizado com sucesso!')
            return redirect(voltar)
    if modal:
        return _render_index(request, manual_form=form)
    return render(request, 'financeiro/lancamento-manual.html', {
        'form': form, 'registro': registro,
        'titulo': 'Novo lançamento' if registro is None else 'Editar lançamento',
        'voltar_url': voltar,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def novo_lancamento(request):
    return _lancamento_manual(request)


@login_required
@require_http_methods(['GET', 'POST'])
def editar_manual(request, pk):
    return _lancamento_manual(request, pk=pk)
