import base64
import binascii
import uuid
from datetime import timedelta
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .client import EvolutionClient, EvolutionError, url_base_webhook
from .models import ConexaoWhatsApp


LEASE_DURATION = timedelta(minutes=5)
MAX_QR_BYTES = 128 * 1024
STATES = {
    'open': ConexaoWhatsApp.Estado.CONECTADO,
    'connecting': ConexaoWhatsApp.Estado.CONECTANDO,
    'close': ConexaoWhatsApp.Estado.DESCONECTADO,
    'closed': ConexaoWhatsApp.Estado.DESCONECTADO,
}


def _resposta(empresa_id, estado, *, qr_code=None):
    messages = {
        ConexaoWhatsApp.Estado.DESCONECTADO: 'O WhatsApp desta empresa está desconectado.',
        ConexaoWhatsApp.Estado.CONECTANDO: 'A conexão está sendo preparada. Consulte o estado em alguns instantes.',
        ConexaoWhatsApp.Estado.AGUARDANDO_QR: 'Leia o QR Code no WhatsApp do número desta empresa.',
        ConexaoWhatsApp.Estado.CONECTADO: 'O WhatsApp desta empresa está conectado.',
        ConexaoWhatsApp.Estado.ERRO: 'Não foi possível confirmar o estado da conexão.',
    }
    response = {'ok': True, 'empresa_id': empresa_id, 'estado': estado, 'mensagem': messages[estado]}
    if qr_code:
        response['qr_code'] = qr_code
    return response


def _webhook(conexao, base):
    return {
        'enabled': True,
        'url': base + reverse('whatsapp:webhook', kwargs={'identificador': conexao.identificador}),
        'headers': {'X-Mediata-Webhook-Secret': conexao.webhook_secret},
        'byEvents': False,
        'base64': False,
        'events': ['CONNECTION_UPDATE'],
    }


def _estado_provider(payload):
    instance = payload.get('instance')
    if not isinstance(instance, dict):
        raise EvolutionError('invalid_response')
    state = instance.get('state', instance.get('status'))
    if not isinstance(state, str) or state not in STATES:
        raise EvolutionError('invalid_response')
    return STATES[state]


def _qr_code(payload):
    qr = payload.get('qrcode', payload)
    raw = qr.get('base64') if isinstance(qr, dict) else None
    if raw is None or raw == '':
        return None
    if not isinstance(raw, str) or len(raw) > MAX_QR_BYTES * 2:
        raise EvolutionError('invalid_response')
    prefix = 'data:image/png;base64,'
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error):
        raise EvolutionError('invalid_response') from None
    if not decoded.startswith(b'\x89PNG\r\n\x1a\n') or len(decoded) > MAX_QR_BYTES:
        raise EvolutionError('invalid_response')
    return prefix + raw


def _reservar_operacao(empresa, *, criar=False):
    with transaction.atomic():
        if criar:
            conexao, _ = ConexaoWhatsApp.objects.get_or_create(empresa=empresa)
        else:
            conexao = ConexaoWhatsApp.objects.filter(empresa=empresa).first()
            if conexao is None:
                return None, None
        conexao = ConexaoWhatsApp.objects.select_for_update().get(pk=conexao.pk)
        now = timezone.now()
        if conexao.operacao_id and conexao.operacao_iniciada_em and conexao.operacao_iniciada_em > now - LEASE_DURATION:
            raise EvolutionError('busy')
        token = uuid.uuid4()
        conexao.operacao_id = token
        conexao.operacao_iniciada_em = now
        conexao.save(update_fields=['operacao_id', 'operacao_iniciada_em', 'atualizado_em'])
        return conexao, token


def _concluir_operacao(conexao, token, estado, *, preservar_callback=False):
    with transaction.atomic():
        current = ConexaoWhatsApp.objects.select_for_update().get(pk=conexao.pk)
        if current.operacao_id != token:
            raise EvolutionError('busy')
        if (
            preservar_callback and current.estado == ConexaoWhatsApp.Estado.CONECTADO
            and current.ultimo_evento_em and current.operacao_iniciada_em
            and current.ultimo_evento_em >= current.operacao_iniciada_em
        ):
            estado = current.estado
        current.estado = estado
        current.operacao_id = None
        current.operacao_iniciada_em = None
        current.save(update_fields=['estado', 'operacao_id', 'operacao_iniciada_em', 'atualizado_em'])
        return estado


def _liberar_operacao(conexao, token):
    ConexaoWhatsApp.objects.filter(pk=conexao.pk, operacao_id=token).update(
        operacao_id=None, operacao_iniciada_em=None,
    )


def conectar_empresa(empresa):
    base_webhook = url_base_webhook()
    client = EvolutionClient()
    conexao, token = _reservar_operacao(empresa, criar=True)
    try:
        webhook = _webhook(conexao, base_webhook)
        if conexao.instancia_criada:
            try:
                existing = client.estado_instancia(conexao.nome_instancia)
            except EvolutionError as error:
                if error.provider_status != 404:
                    raise
                conexao.instancia_criada = False
            else:
                instance = existing.get('instance')
                if (
                    isinstance(instance, dict)
                    and instance.get('instanceName') == conexao.nome_instancia
                    and instance.get('state', instance.get('status')) is None
                ):
                    conexao.instancia_criada = False
                else:
                    _estado_provider(existing)
        if not conexao.instancia_criada:
            try:
                client.criar_instancia(conexao.nome_instancia, webhook)
            except EvolutionError as error:
                # Um timeout anterior pode ter criado a instância remota.
                if error.provider_status not in (400, 403, 409):
                    raise
                _estado_provider(client.estado_instancia(conexao.nome_instancia))
            ConexaoWhatsApp.objects.filter(pk=conexao.pk, operacao_id=token).update(instancia_criada=True)
        client.configurar_webhook(conexao.nome_instancia, webhook)
        payload = client.conectar_instancia(conexao.nome_instancia)
        qr = _qr_code(payload)
        if qr:
            estado = ConexaoWhatsApp.Estado.AGUARDANDO_QR
        elif isinstance(payload.get('instance'), dict):
            estado = _estado_provider(payload)
        elif any(key in payload for key in ('base64', 'code', 'count')):
            # O provedor pode responder antes da primeira imagem ficar pronta.
            estado = ConexaoWhatsApp.Estado.CONECTANDO
        else:
            raise EvolutionError('invalid_response')
        estado = _concluir_operacao(conexao, token, estado, preservar_callback=True)
        return _resposta(empresa.pk, estado, qr_code=qr if estado == ConexaoWhatsApp.Estado.AGUARDANDO_QR else None)
    finally:
        _liberar_operacao(conexao, token)


def consultar_status_empresa(empresa):
    client = EvolutionClient()
    conexao = ConexaoWhatsApp.objects.filter(empresa=empresa).first()
    if conexao is None or not conexao.instancia_criada:
        return _resposta(empresa.pk, ConexaoWhatsApp.Estado.DESCONECTADO)
    if conexao.operacao_id is not None:
        return _resposta(empresa.pk, conexao.estado)
    payload = client.estado_instancia(conexao.nome_instancia)
    estado = _estado_provider(payload)
    if estado == ConexaoWhatsApp.Estado.CONECTANDO and conexao.estado == ConexaoWhatsApp.Estado.AGUARDANDO_QR:
        estado = conexao.estado
    updated = ConexaoWhatsApp.objects.filter(
        pk=conexao.pk, operacao_id__isnull=True, atualizado_em=conexao.atualizado_em,
    ).update(
        estado=estado, atualizado_em=timezone.now(),
    )
    if not updated:
        # Callback ou ação posterior à consulta prevalece sobre a resposta antiga.
        estado = ConexaoWhatsApp.objects.filter(empresa=empresa).values_list('estado', flat=True).first()
        estado = estado or ConexaoWhatsApp.Estado.DESCONECTADO
    return _resposta(empresa.pk, estado)


def desconectar_empresa(empresa):
    client = EvolutionClient()
    conexao, token = _reservar_operacao(empresa)
    if conexao is None:
        return _resposta(empresa.pk, ConexaoWhatsApp.Estado.DESCONECTADO)
    try:
        if conexao.instancia_criada:
            estado = _estado_provider(client.estado_instancia(conexao.nome_instancia))
            if estado != ConexaoWhatsApp.Estado.DESCONECTADO:
                client.desconectar_instancia(conexao.nome_instancia)
        estado = _concluir_operacao(conexao, token, ConexaoWhatsApp.Estado.DESCONECTADO)
        return _resposta(empresa.pk, estado)
    finally:
        _liberar_operacao(conexao, token)
