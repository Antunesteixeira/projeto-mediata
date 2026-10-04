from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate
from django.contrib.auth import login as login_django
from django.contrib.auth.decorators import login_required

from django.http import Http404
from tickets.models import Ticket
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
from .dashboard import build_dashboard_context

# views.py
from django.views.generic import DetailView

# core/views.py
from django.views.generic import CreateView, UpdateView, DetailView, ListView
from django.urls import reverse_lazy
from .models import Empresa, HorarioFuncionamento, Funcionario, Servico
from .forms import EmpresaForm, HorarioFuncionamentoForm, FuncionarioForm, ServicoForm

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
def dashboard(request):
    empresa = Empresa.objects.first()
    if empresa is None:
        # Se não houver empresa cadastrada, redireciona para o cadastro
        messages.info(request, 'Por favor, cadastre a empresa antes de acessar o dashboard.')
        return redirect('empresa_cadastrar')

    can_view_all = request.user.is_superuser or has_role(request.user, 'gerente')
    tickets = Ticket.objects.all()
    if not can_view_all:
        tickets = tickets.filter(usuario=request.user)
    context = build_dashboard_context(tickets, empresa, can_view_all, now=timezone.now())
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
