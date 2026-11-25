import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.models import Empresa
from core.tenancy import empresa_do_usuario, pode_gerenciar_empresa

from .client import EvolutionError, configuracao_disponivel
from .forms import SelecionarEmpresaWhatsAppForm
from .models import ConexaoWhatsApp
from . import services


MAX_WEBHOOK_BYTES = 64 * 1024


def _empresas(user):
    if not pode_gerenciar_empresa(user):
        raise PermissionDenied('A configuração do WhatsApp é restrita aos gerentes da empresa.')
    empresas = Empresa.objects.filter(ativo=True)
    if not user.is_superuser:
        empresas = empresas.filter(pk=empresa_do_usuario(user).pk)
    return empresas.order_by('nome_fantasia')


def _empresa(user, empresa_id):
    return get_object_or_404(_empresas(user), pk=empresa_id)


def _render_configuracao(request, empresa=None):
    empresas = _empresas(request.user)
    conexao = ConexaoWhatsApp.objects.filter(empresa=empresa).first() if empresa else None
    context = {
        'empresas': empresas, 'empresa_selecionada': empresa, 'conexao': conexao,
        'estado_inicial': conexao.estado if conexao else ConexaoWhatsApp.Estado.DESCONECTADO,
        'evolution_disponivel': configuracao_disponivel(),
    }
    if empresa is not None:
        for action in ('conectar', 'status', 'desconectar'):
            context[f'url_{action}'] = reverse(f'whatsapp:{action}', kwargs={'empresa_id': empresa.pk})
    response = render(request, 'whatsapp/index.html', context)
    patch_vary_headers(response, ('Cookie',))
    return response


@login_required
@never_cache
@require_GET
def index(request):
    empresas = _empresas(request.user)
    form = SelecionarEmpresaWhatsAppForm(request.GET)
    if not form.is_valid():
        raise Http404('Empresa não encontrada.')
    empresa_id = form.cleaned_data.get('empresa_id')
    empresa = _empresa(request.user, empresa_id) if empresa_id else None
    if empresa is None and not request.user.is_superuser:
        empresa = get_object_or_404(empresas)
    return _render_configuracao(request, empresa)


@login_required
@never_cache
@require_GET
def configurar(request, empresa_id):
    return _render_configuracao(request, _empresa(request.user, empresa_id))


def _acao(request, empresa_id, action):
    empresa = _empresa(request.user, empresa_id)
    try:
        data = action(empresa)
    except EvolutionError as error:
        data = {
            'ok': False, 'empresa_id': empresa.pk,
            'estado': ConexaoWhatsApp.Estado.ERRO, 'mensagem': error.mensagem,
        }
        response = JsonResponse(data, status=error.status_code)
    else:
        response = JsonResponse(data)
    patch_vary_headers(response, ('Cookie',))
    return response


@login_required
@never_cache
@require_POST
def conectar(request, empresa_id):
    return _acao(request, empresa_id, services.conectar_empresa)


@login_required
@never_cache
@require_GET
def status(request, empresa_id):
    return _acao(request, empresa_id, services.consultar_status_empresa)


@login_required
@never_cache
@require_POST
def desconectar(request, empresa_id):
    return _acao(request, empresa_id, services.desconectar_empresa)


@csrf_exempt
@never_cache
@require_POST
def webhook(request, identificador):
    content_length = request.META.get('CONTENT_LENGTH')
    if content_length:
        try:
            if int(content_length) > MAX_WEBHOOK_BYTES:
                return JsonResponse({'ok': False}, status=413)
        except (TypeError, ValueError):
            return JsonResponse({'ok': False}, status=400)
    conexao = ConexaoWhatsApp.objects.select_related('empresa').filter(identificador=identificador).first()
    expected = conexao.webhook_secret if conexao else '0' * 64
    supplied = request.headers.get('X-Mediata-Webhook-Secret', '')
    authenticated = constant_time_compare(supplied, expected)
    if not authenticated or conexao is None or not conexao.empresa.ativo:
        return JsonResponse({'ok': False}, status=403)
    if request.content_type != 'application/json':
        return JsonResponse({'ok': False}, status=415)
    raw = request.read(MAX_WEBHOOK_BYTES + 1)
    if len(raw) > MAX_WEBHOOK_BYTES:
        return JsonResponse({'ok': False}, status=413)
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return JsonResponse({'ok': False}, status=400)
    if not isinstance(payload, dict) or payload.get('instance') != conexao.nome_instancia:
        return JsonResponse({'ok': False}, status=403)
    event = payload.get('event')
    if not isinstance(event, str) or event.replace('.', '_').replace('-', '_').upper() != 'CONNECTION_UPDATE':
        return JsonResponse({'ok': True, 'ignorado': True})
    data = payload.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('state'), str) or data['state'] not in services.STATES:
        return JsonResponse({'ok': False}, status=400)
    now = timezone.now()
    ConexaoWhatsApp.objects.filter(pk=conexao.pk).update(
        estado=services.STATES[data['state']], instancia_criada=True,
        ultimo_evento_em=now, atualizado_em=now,
    )
    return JsonResponse({'ok': True})
