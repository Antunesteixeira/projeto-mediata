from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as login_django
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from insumos.models import Insumos
from tickets.models import Ticket
from usuarios.access import is_assinante
from .dashboard import build_dashboard_context
from .forms import EmpresaForm
from .models import Empresa
from .tenancy import (
    dados_da_empresa, empresa_do_usuario, pode_gerenciar_empresa,
    pode_acessar_financeiro, pode_operar_tickets, tickets_da_empresa, usuarios_da_empresa,
)


def index(request):
    if is_assinante(request.user):
        return redirect('index-tickets')
    return render(request, 'index.html')


def login(request):
    if request.method == 'GET':
        return redirect('dashboard') if request.user.is_authenticated else render(request, 'registration/login.html')
    user = authenticate(username=request.POST.get('username'), password=request.POST.get('password'))
    if user:
        login_django(request, user)
        return redirect('dashboard')
    return redirect('login')


@login_required
def dashboard(request):
    if is_assinante(request.user):
        return redirect('index-tickets')
    if not request.user.is_superuser and empresa_do_usuario(request.user) is None:
        raise PermissionDenied('Sua conta precisa estar vinculada a uma empresa ativa.')
    if not pode_operar_tickets(request.user):
        return redirect('index-tickets')
    empresa = empresa_do_usuario(request.user)
    if request.user.is_superuser and empresa is None:
        empresa = Empresa.objects.order_by('pk').first()
    if empresa is None:
        messages.info(request, 'Cadastre a primeira empresa para iniciar a operação.')
        return redirect('empresa_cadastrar')
    context = build_dashboard_context(
        tickets_da_empresa(request.user), empresa, True, now=timezone.now(),
        is_platform_admin=request.user.is_superuser,
        can_view_financial=pode_acessar_financeiro(request.user),
    )
    return render(request, 'home/dashboard.html', context)


@login_required
def erro_404(request, exception):
    return render(request, '404.html', status=404)


@login_required
@require_GET
def buscar_itens(request):
    if not pode_acessar_financeiro(request.user):
        raise PermissionDenied('A consulta de preços é restrita à gestão da empresa.')
    termo = request.GET.get('term', '').strip()
    itens = dados_da_empresa(request.user, Insumos.objects.all())
    itens = itens.filter(Q(insumo__icontains=termo) | Q(codigo__icontains=termo)).order_by('insumo')[:10] if termo else []
    return JsonResponse([{
        'id': item.id,
        'label': f'{item.insumo} ({item.codigo}) - {item.get_tipo_display()}',
        'value': item.insumo,
        'codigo': item.codigo,
        'tipo': item.tipo,
        'tipo_display': item.get_tipo_display(),
        'unidade': item.unidade,
        'unidade_display': item.get_unidade_display() if item.unidade else '',
        'valor_unit': str(item.valor_unit) if item.valor_unit else '0.00',
    } for item in itens], safe=False)


class EmpresaScopedMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not pode_gerenciar_empresa(request.user):
            raise PermissionDenied('A administração da empresa é restrita aos gerentes.')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        if not pode_gerenciar_empresa(self.request.user):
            raise PermissionDenied('A administração da empresa é restrita aos gerentes.')
        queryset = Empresa.objects.all()
        if self.request.user.is_superuser:
            return queryset
        company = empresa_do_usuario(self.request.user)
        if company is None:
            raise PermissionDenied('Sua conta precisa estar vinculada a uma empresa ativa.')
        return queryset.filter(pk=company.pk)


class EmpresaCreateView(LoginRequiredMixin, CreateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = 'empresa/cadastro-empresa.html'
    success_url = reverse_lazy('empresa_success')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_superuser:
            raise PermissionDenied('Somente o administrador pode cadastrar empresas.')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, 'Empresa cadastrada com sucesso!')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Por favor, corrija os erros abaixo.')
        return super().form_invalid(form)


class EmpresaUpdateView(EmpresaScopedMixin, UpdateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = 'empresa/cadastro-empresa.html'
    success_url = reverse_lazy('empresa_success')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not pode_gerenciar_empresa(request.user):
            raise PermissionDenied('Somente gerentes podem alterar a empresa.')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, 'Empresa atualizada com sucesso!')
        return super().form_valid(form)


class EmpresaDetailView(EmpresaScopedMixin, DetailView):
    model = Empresa
    template_name = 'empresa/perfil-empresa.html'
    context_object_name = 'empresa'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.object
        context['equipe_usuarios'] = usuarios_da_empresa(self.request.user).filter(
            vinculo_empresa__empresa=company,
        ).prefetch_related('groups')
        context['tickets_empresa'] = tickets_da_empresa(self.request.user).filter(
            empresa=company,
        ).select_related('usuario').order_by('-data_criacao')[:10]
        context['pode_editar_empresa'] = pode_gerenciar_empresa(self.request.user)
        return context


class EmpresaListView(EmpresaScopedMixin, ListView):
    model = Empresa
    template_name = 'empresa/lista_empresas.html'
    context_object_name = 'empresas'


@login_required
def success_view(request):
    if not pode_gerenciar_empresa(request.user):
        raise PermissionDenied('A administração da empresa é restrita aos gerentes.')
    return render(request, 'empresa/success.html')


@login_required
def empresa_cadastrar(request):
    return EmpresaCreateView.as_view()(request)


@login_required
def empresa_editar(request, pk):
    return EmpresaUpdateView.as_view()(request, pk=pk)


@login_required
def empresa_perfil(request, pk):
    return EmpresaDetailView.as_view()(request, pk=pk)


@login_required
def empresa_lista(request):
    return EmpresaListView.as_view()(request)


@login_required
def uploader_arquivos(request):
    if not pode_gerenciar_empresa(request.user):
        raise PermissionDenied('O envio de arquivos é restrito à gestão da empresa.')
    return render(request, 'uploader_arquivos.html')
