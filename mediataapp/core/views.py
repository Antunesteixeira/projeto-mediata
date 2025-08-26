from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, logout
from django.contrib.auth import login as login_django
from django.contrib.auth.decorators import login_required

from django.http import Http404
from tickets.models import Ticket, Orcamento, Pagamentos
from insumos.models import Insumos 

from rolepermissions.checkers import has_role

from django.contrib.auth.models import User, Group

from django.http import JsonResponse
from django.views import View

from django.views.decorators.http import require_GET

from django.db.models import Q
from django.utils import timezone
import logging

# views.py
from django.contrib import messages
from .models import Empresa

# views.py
from django.views.generic import DetailView

# core/views.py
from django.views.generic import CreateView, UpdateView, DetailView, ListView
from django.urls import reverse_lazy
from .models import Empresa, HorarioFuncionamento, Funcionario, Servico
from .forms import EmpresaForm, HorarioFuncionamentoForm, FuncionarioForm, ServicoForm

from django.db.models import Sum, Case, When, Value, IntegerField, F, Prefetch


logger = logging.getLogger(__name__)


def index(request):
    return render(request, 'index.html')
    
def login(request):
    if request.method == "GET":
        if request.user.is_authenticated:
            return redirect('/dashboard/')
        else:
            return render(request, 'registration/login.html')
    else: 
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(username=username, password=password)

        if user:
            login_django(request, user)
            return redirect('/dashboard/')
        else:
            return redirect('accounts/login/')
        
@login_required
def sair(request):
    logout(request)
    return redirect('/')

@login_required
def dashboard(request):
    usuario = request.user
    hoje = timezone.now()
    
    if not Empresa.objects.exists():
        # Se não houver empresa cadastrada, redireciona para o cadastro
        messages.info(request, 'Por favor, cadastre a empresa antes de acessar o dashboard.')
        return redirect('empresa_cadastrar')

    # Tickets base
    tickets = Ticket.objects.filter(
        usuario=usuario,
        status__in=["V", "X", "E", "A"]
    ).annotate(
        custom_order=Case(
            When(status='L', then=Value(0)),
            When(status='A', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by('custom_order')

    # Se for superuser ou gerente -> vê todos
    if usuario.is_superuser or has_role(usuario, [User, 'gerente']):
        tickets_total = Ticket.objects.count()
        orcamentos = Orcamento.objects.filter(
            data_criacao__year=hoje.year,
            data_criacao__month=hoje.month
        )
        tickets = Ticket.objects.all()
    else:
        tickets_total = Ticket.objects.filter(usuario=usuario).count()
        orcamentos = Orcamento.objects.filter(
            ticket_orcamento__usuario=usuario,
            data_criacao__year=hoje.year,
            data_criacao__month=hoje.month
        )
        tickets = Ticket.objects.filter(usuario=usuario)

    # Soma do valor total de orçamentos no mês
    total_mes = orcamentos.aggregate(total=Sum('valor_total'))['total'] or 0

    # Calcula totais de orçamentos e pagamentos por ticket
    tickets = tickets.prefetch_related(
        Prefetch("orcamento_set", queryset=Orcamento.objects.all(), to_attr="orcamentos_prefetch"),
        Prefetch("pagamentos", queryset=Pagamentos.objects.all(), to_attr="pagamentos_prefetch"),
    )

    for ticket in tickets:
        ticket.total_orcamentos = sum([orc.valor_total for orc in getattr(ticket, "orcamentos_prefetch", [])])
        ticket.total_pagamentos = sum([pag.valor_pagamento for pag in getattr(ticket, "pagamentos_prefetch", [])])

    # Calcula métricas gerais
    orcamento_total = sum([ticket.total_orcamentos for ticket in tickets])
    total_pagamentos = sum([ticket.total_pagamentos for ticket in tickets])
    total_lucros = orcamento_total - total_pagamentos

    context = {
        'tickets': tickets,
        'tickets_total': tickets_total,
        "orcamentos": orcamentos,
        "total_mes": total_mes,
        "total_lucros": total_lucros,
    }

    return render(request, 'home/dashboard.html', context)

@login_required
def erro_404(request, exception):
    return render(request, '404.html', status=404)

@login_required
@require_GET
def buscar_itens(request):
    termo = request.GET.get('term', '').strip()
    
    if termo:
        itens = Insumos.objects.filter(
            Q(insumo__icontains=termo) | 
            Q(codigo__icontains=termo)
        ).order_by('insumo')[:10]
        
        resultados = [{
            'id': item.id,
            'label': f"{item.insumo} ({item.codigo}) - {item.get_tipo_display()}",
            'value': item.insumo,
            'codigo': item.codigo,
            'tipo': item.tipo,
            'tipo_display': item.get_tipo_display(),
            'unidade': item.unidade,
            'unidade_display': item.get_unidade_display() if item.unidade else '',
            'valor_unit': str(item.valor_unit) if item.valor_unit else '0.00'
        } for item in itens]
    else:
        resultados = []
    
    return JsonResponse(resultados, safe=False)


class EmpresaCreateView(CreateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = 'empresa/cadastro-empresa.html'
    success_url = reverse_lazy('empresa_success')
    
    def form_valid(self, form):
        messages.success(self.request, 'Empresa cadastrada com sucesso!')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Por favor, corrija os erros abaixo.')
        return super().form_invalid(form)


class EmpresaUpdateView(UpdateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = 'empresa/cadastro-empresa.html'
    success_url = reverse_lazy('empresa_success')
    
    def form_valid(self, form):
        messages.success(self.request, 'Empresa atualizada com sucesso!')
        return super().form_valid(form)

# View baseada em classe para visualizar perfil da empresa
class EmpresaDetailView(DetailView):
    model = Empresa
    template_name = 'empresa/perfil-empresa.html'
    context_object_name = 'empresa'

# View baseada em classe para listar empresas
class EmpresaListView(ListView):
    model = Empresa
    template_name = 'empresa/lista_empresas.html'
    context_object_name = 'empresas'
    
    def get_queryset(self):
        return Empresa.objects.filter(ativo=True)

# View baseada em função para sucesso (pode manter como função)
@login_required
def success_view(request):
    return render(request, 'empresa/success.html')

# Views baseadas em função alternativas (se preferir)
@login_required
def empresa_cadastrar(request):
    if request.method == 'POST':
        form = EmpresaForm(request.POST)
        if form.is_valid():
            empresa = form.save()
            messages.success(request, 'Empresa cadastrada com sucesso!')
            return redirect('empresa_success')
        else:
            messages.error(request, 'Por favor, corrija os erros abaixo.')
    else:
        form = EmpresaForm()
    
    return render(request, 'empresa/cadastro_empresa.html', {'form': form})

@login_required
def empresa_editar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    
    if request.method == 'POST':
        form = EmpresaForm(request.POST, instance=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, 'Empresa atualizada com sucesso!')
            return redirect('empresa_success')
        else:
            messages.error(request, 'Por favor, corrija os erros abaixo.')
    else:
        form = EmpresaForm(instance=empresa)
    
    return render(request, 'empresa/cadastro_empresa.html', {'form': form})

@login_required
def empresa_perfil(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    return render(request, 'empresa/perfil-empresa.html', {'empresa': empresa})

@login_required
def empresa_lista(request):
    empresas = Empresa.objects.filter(ativo=True)
    return render(request, 'empresa/lista_empresas.html', {'empresas': empresas})

@login_required
def uploader_arquivos(request):
    return render(request, 'uploader_arquivos.html')