"""Prévia e envio operacional para o único responsável atual do ticket."""

import json
import re
import uuid
from datetime import timedelta

from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import salted_hmac

from core.tenancy import pode_operar_tickets, tickets_da_empresa

from .client import EvolutionClient, EvolutionError
from .models import ConexaoWhatsApp, EnvioTicketWhatsApp


CONFIRMACAO_SALT = 'whatsapp.ticket.envio.v1'
CONFIRMACAO_MAX_AGE = 5 * 60
CONTEUDO_RECENTE = timedelta(minutes=2)
PROCESSAMENTO_MAXIMO = timedelta(minutes=5)
MENSAGENS_ESTADO = {
    EnvioTicketWhatsApp.Estado.PROCESSANDO: 'O envio está em processamento. Aguarde e confira antes de tentar novamente.',
    EnvioTicketWhatsApp.Estado.ACEITO: 'Mensagem aceita pelo serviço WhatsApp. Isso não confirma entrega ou leitura.',
    EnvioTicketWhatsApp.Estado.FALHOU: 'A mensagem não foi enviada. Revise os dados e a conexão antes de abrir uma nova prévia.',
    EnvioTicketWhatsApp.Estado.INCERTO: 'Não foi possível confirmar o resultado. Confira a conversa com o responsável no WhatsApp da empresa antes de enviar novamente.',
}


class TicketWhatsAppError(Exception):
    def __init__(self, mensagem, *, status_code=400):
        self.mensagem = mensagem
        self.status_code = status_code
        super().__init__(mensagem)


def normalizar_telefone(value):
    if not isinstance(value, str) or not re.fullmatch(r'\+?[0-9\s().-]+', value.strip()):
        raise TicketWhatsAppError('Informe um telefone válido no cadastro do colaborador, com DDD ou DDI.')
    value = value.strip()
    explicit = value.startswith('+')
    digits = re.sub(r'[^0-9]', '', value)
    if not explicit and len(digits) in (10, 11):
        if digits[0] == '0' or digits[2] in '01':
            raise TicketWhatsAppError('O telefone do colaborador precisa conter um DDD e um número válidos.')
        digits = '55' + digits
    elif not explicit and not (12 <= len(digits) <= 15):
        raise TicketWhatsAppError('Informe o telefone do colaborador com DDD ou com DDI explícito.')
    if not 8 <= len(digits) <= 15 or digits.startswith('0') or len(set(digits)) < 2:
        raise TicketWhatsAppError('O telefone do colaborador não é válido.')
    if digits.startswith('55') and (
        len(digits) not in (12, 13) or digits[2] == '0' or digits[4] in '01'
    ):
        raise TicketWhatsAppError('O telefone brasileiro do colaborador precisa conter DDD e número válidos.')
    return digits


def mascarar_telefone(numero):
    if numero.startswith('55'):
        return f'+55 ** *****-{numero[-4:]}'
    return f'+*** ******{numero[-4:]}'


def _ticket_atual(ticket, usuario, *, bloquear=False):
    if not pode_operar_tickets(usuario):
        raise PermissionDenied('Seu perfil não permite enviar tickets pelo WhatsApp.')
    queryset = tickets_da_empresa(usuario)
    if bloquear:
        queryset = queryset.select_for_update(of=('self',))
    return get_object_or_404(queryset.select_related('empresa', 'colaborador'), key=ticket.key)


def _snapshot(ticket):
    if ticket.empresa_id is None or not ticket.empresa.ativo:
        raise TicketWhatsAppError('O ticket precisa estar vinculado a uma empresa ativa.', status_code=409)
    colaborador = ticket.colaborador
    if colaborador is None:
        raise TicketWhatsAppError('Vincule um colaborador ao ticket antes de enviar.', status_code=409)
    if not colaborador.ativo or colaborador.empresa_id != ticket.empresa_id:
        raise TicketWhatsAppError('O responsável precisa estar ativo e pertencer à empresa do ticket.', status_code=409)
    numero = normalizar_telefone(colaborador.telefone)
    conexao = ConexaoWhatsApp.objects.filter(empresa_id=ticket.empresa_id).first()
    if (
        conexao is None or not conexao.instancia_criada
        or conexao.estado != ConexaoWhatsApp.Estado.CONECTADO
        or conexao.operacao_id is not None
    ):
        raise TicketWhatsAppError('O WhatsApp da empresa precisa estar conectado antes do envio.', status_code=503)
    nome = str(colaborador)
    mensagem = '\n'.join((
        f'Ticket #{ticket.ticket}',
        f'Situação: {ticket.get_status_display()}',
        f'Previsão de conclusão: {ticket.data_finalizar.strftime("%d/%m/%Y") if ticket.data_finalizar else "Não informada"}',
        f'Emergencial: {"Sim" if ticket.emergencial else "Não"}',
        '', 'Descrição:', ticket.descricao.strip(),
    ))
    values = {
        'ticket': str(ticket.key), 'empresa': ticket.empresa_id, 'autor': ticket.usuario_id,
        'colaborador': colaborador.pk, 'nome': nome, 'telefone': numero,
        'numero_ticket': ticket.ticket, 'status': ticket.status,
        'previsao': ticket.data_finalizar.isoformat() if ticket.data_finalizar else None,
        'descricao': ticket.descricao, 'emergencial': ticket.emergencial,
        'conexao': str(conexao.identificador), 'mensagem': mensagem,
    }
    fingerprint = salted_hmac(
        'whatsapp.ticket-message.snapshot',
        json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(',', ':')),
        algorithm='sha256',
    ).hexdigest()
    return {
        'ticket': ticket, 'colaborador': colaborador, 'conexao': conexao,
        'numero': numero, 'nome': nome, 'mensagem': mensagem, 'fingerprint': fingerprint,
        'telefone_mascarado': mascarar_telefone(numero),
    }


def _registros(ticket):
    return EnvioTicketWhatsApp.objects.filter(ticket_id=ticket.pk, empresa_id=ticket.empresa_id)


def _resumo(registro):
    if registro is None:
        return None
    estado = registro.estado
    if estado == EnvioTicketWhatsApp.Estado.PROCESSANDO and registro.atualizado_em <= timezone.now() - PROCESSAMENTO_MAXIMO:
        # Apenas apresentação: a transição persistida exige o lock do POST.
        estado = EnvioTicketWhatsApp.Estado.INCERTO
    usuario = registro.usuario
    return {
        'estado': estado, 'mensagem': MENSAGENS_ESTADO[estado],
        'criado_em': registro.criado_em.isoformat(),
        'usuario': (usuario.get_full_name().strip() or usuario.get_username()) if usuario else 'Usuário removido',
    }


def montar_previa(ticket, usuario):
    ticket = _ticket_atual(ticket, usuario)
    snap = _snapshot(ticket)
    EvolutionClient()  # Verifica configuração local, sem qualquer requisição.
    confirmacao = signing.dumps({
        'nonce': str(uuid.uuid4()), 'ticket': str(ticket.key),
        'usuario': usuario.pk, 'fingerprint': snap['fingerprint'],
    }, salt=CONFIRMACAO_SALT)
    ultimo = _registros(ticket).select_related('usuario').first()
    return {
        'ok': True, 'numero_ticket': ticket.ticket,
        'destinatario': {'nome': snap['nome'], 'telefone_mascarado': snap['telefone_mascarado']},
        'mensagem': snap['mensagem'], 'confirmacao': confirmacao, 'ultimo_envio': _resumo(ultimo),
    }


def _ler_confirmacao(confirmacao, ticket, usuario):
    if not isinstance(confirmacao, str) or not confirmacao or len(confirmacao) > 2048:
        raise TicketWhatsAppError('Abra a prévia e confirme os dados antes de enviar.')
    expired = False
    try:
        try:
            values = signing.loads(confirmacao, salt=CONFIRMACAO_SALT, max_age=CONFIRMACAO_MAX_AGE)
        except signing.SignatureExpired:
            # Uma chave antiga pode somente consultar o resultado já registrado.
            values = signing.loads(confirmacao, salt=CONFIRMACAO_SALT)
            expired = True
        if (
            not isinstance(values, dict) or values.get('ticket') != str(ticket.key)
            or values.get('usuario') != usuario.pk
            or not isinstance(values.get('fingerprint'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', values['fingerprint'])
        ):
            raise ValueError
        values['nonce'] = uuid.UUID(values['nonce'])
    except (signing.BadSignature, TypeError, ValueError, KeyError):
        raise TicketWhatsAppError('A confirmação não é válida. Abra uma nova prévia.') from None
    return values, expired


def _resultado(registro, *, http_status=None):
    estado = registro.estado
    body = {
        'ok': estado == EnvioTicketWhatsApp.Estado.ACEITO,
        'estado': estado, 'envio_id': registro.pk,
        'mensagem': MENSAGENS_ESTADO[estado],
        'ultimo_envio': _resumo(registro),
    }
    default_status = 200 if body['ok'] else 409 if estado in (
        EnvioTicketWhatsApp.Estado.PROCESSANDO, EnvioTicketWhatsApp.Estado.INCERTO,
    ) else 502
    return body, http_status or default_status


def _resultado_incerto(registro):
    return {
        'ok': False, 'estado': EnvioTicketWhatsApp.Estado.INCERTO,
        'envio_id': registro.pk, 'mensagem': MENSAGENS_ESTADO[EnvioTicketWhatsApp.Estado.INCERTO],
    }, 502


def _recuperar_processamento(registro, now):
    if registro.estado != EnvioTicketWhatsApp.Estado.PROCESSANDO or registro.atualizado_em > now - PROCESSAMENTO_MAXIMO:
        return False
    changed = EnvioTicketWhatsApp.objects.filter(
        pk=registro.pk, estado=EnvioTicketWhatsApp.Estado.PROCESSANDO,
        atualizado_em=registro.atualizado_em,
    ).update(
        estado=EnvioTicketWhatsApp.Estado.INCERTO, codigo_resultado='resultado_nao_confirmado',
        atualizado_em=now, finalizado_em=now,
    )
    registro.refresh_from_db()
    return bool(changed)


def _reservar_envio(ticket, usuario, values, expired):
    with transaction.atomic():
        ticket = _ticket_atual(ticket, usuario, bloquear=True)
        now = timezone.now()
        existing = EnvioTicketWhatsApp.objects.filter(idempotencia=values['nonce']).first()
        if existing is not None:
            if (
                existing.ticket_id != ticket.pk or existing.empresa_id != ticket.empresa_id
                or existing.usuario_id != usuario.pk or existing.fingerprint != values['fingerprint']
            ):
                raise TicketWhatsAppError('A confirmação não corresponde a este envio.')
            _recuperar_processamento(existing, now)
            return None, existing, _resultado(existing)
        if expired:
            raise TicketWhatsAppError('A prévia expirou. Abra uma nova prévia antes de enviar.')
        snap = _snapshot(ticket)
        if snap['fingerprint'] != values['fingerprint']:
            raise TicketWhatsAppError('Os dados do ticket ou do responsável mudaram. Atualize a prévia.', status_code=409)
        pending = _registros(ticket).filter(estado=EnvioTicketWhatsApp.Estado.PROCESSANDO).first()
        if pending is not None:
            _recuperar_processamento(pending, now)
            return None, pending, _resultado(pending, http_status=409)
        recent = _registros(ticket).filter(
            fingerprint=snap['fingerprint'],
            estado__in=(EnvioTicketWhatsApp.Estado.ACEITO, EnvioTicketWhatsApp.Estado.INCERTO),
            atualizado_em__gte=now - CONTEUDO_RECENTE,
        ).first()
        if recent is not None:
            data, status = _resultado(recent, http_status=409)
            if recent.estado == EnvioTicketWhatsApp.Estado.ACEITO:
                data['mensagem'] = 'Este conteúdo já teve envio aceito nos últimos dois minutos. Confira a conversa no WhatsApp da empresa.'
            else:
                data['mensagem'] = 'Existe uma tentativa recente sem confirmação. Confira a conversa no WhatsApp da empresa e aguarde dois minutos antes de tentar novamente.'
            return None, recent, (data, status)
        registro = EnvioTicketWhatsApp.objects.create(
            idempotencia=values['nonce'], empresa_id=ticket.empresa_id,
            ticket=ticket, colaborador=snap['colaborador'], usuario=usuario,
            ticket_numero=ticket.ticket, colaborador_nome=snap['nome'],
            telefone_mascarado=snap['telefone_mascarado'], fingerprint=snap['fingerprint'],
        )
        return snap, registro, None


def _finalizar_envio(registro, estado, codigo, *, id_provedor=''):
    try:
        now = timezone.now()
        changed = EnvioTicketWhatsApp.objects.filter(
            pk=registro.pk, idempotencia=registro.idempotencia,
            estado=EnvioTicketWhatsApp.Estado.PROCESSANDO,
        ).update(
            estado=estado, codigo_resultado=codigo, id_provedor=id_provedor,
            atualizado_em=now, finalizado_em=now,
        )
        if changed:
            registro.estado = estado
            registro.codigo_resultado = codigo
            registro.id_provedor = id_provedor
            registro.atualizado_em = now
            registro.finalizado_em = now
        else:
            registro.refresh_from_db()
        return registro
    except DatabaseError:
        # O registro persistido antes do HTTP impede reenvio após perda do resultado.
        return None


def _concluir(registro, estado, codigo, *, http_status=None, id_provedor=''):
    current = _finalizar_envio(registro, estado, codigo, id_provedor=id_provedor)
    if current is None:
        return _resultado_incerto(registro)
    return _resultado(current, http_status=http_status)


def enviar_ticket(ticket, usuario, confirmacao):
    values, expired = _ler_confirmacao(confirmacao, ticket, usuario)
    snap, registro, resultado = _reservar_envio(ticket, usuario, values, expired)
    if resultado is not None:
        return resultado
    try:
        # Replays consultam o registro mesmo quando a integração está desativada.
        client = EvolutionClient()
    except EvolutionError:
        return _concluir(registro, EnvioTicketWhatsApp.Estado.FALHOU, 'configuracao_indisponivel', http_status=503)
    try:
        remote = client.estado_instancia(snap['conexao'].nome_instancia)
        instance = remote.get('instance') if isinstance(remote, dict) else None
        if not isinstance(instance, dict) or instance.get('state') != 'open' or (
            instance.get('instanceName') is not None and instance['instanceName'] != snap['conexao'].nome_instancia
        ):
            return _concluir(registro, EnvioTicketWhatsApp.Estado.FALHOU, 'conexao_inativa', http_status=503)
    except Exception:
        return _concluir(registro, EnvioTicketWhatsApp.Estado.FALHOU, 'status_nao_confirmado', http_status=503)

    # A consulta remota pode demorar; confira novamente os dados antes do envio.
    try:
        with transaction.atomic():
            current_ticket = _ticket_atual(ticket, usuario, bloquear=True)
            current_snap = _snapshot(current_ticket)
            current_envio = EnvioTicketWhatsApp.objects.get(pk=registro.pk)
            if current_envio.estado != EnvioTicketWhatsApp.Estado.PROCESSANDO:
                return _resultado(current_envio)
            if current_snap['fingerprint'] != registro.fingerprint:
                return _concluir(registro, EnvioTicketWhatsApp.Estado.FALHOU, 'dados_alterados', http_status=409)
    except (TicketWhatsAppError, PermissionDenied, Http404):
        return _concluir(registro, EnvioTicketWhatsApp.Estado.FALHOU, 'dados_alterados', http_status=409)
    except DatabaseError:
        return _resultado_incerto(registro)

    try:
        payload = client.enviar_texto(snap['conexao'].nome_instancia, snap['numero'], snap['mensagem'])
    except EvolutionError as error:
        definite = error.provider_status is not None and 400 <= error.provider_status < 500 and error.provider_status != 408
        return _concluir(
            registro, EnvioTicketWhatsApp.Estado.FALHOU if definite else EnvioTicketWhatsApp.Estado.INCERTO,
            'recusado_pelo_servico' if definite else 'resultado_nao_confirmado', http_status=502,
        )
    except Exception:
        return _concluir(registro, EnvioTicketWhatsApp.Estado.INCERTO, 'resultado_nao_confirmado', http_status=502)
    key = payload.get('key') if isinstance(payload, dict) else None
    identifier = key.get('id') if isinstance(key, dict) else None
    if (
        not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', identifier)
        or identifier in (
            getattr(client, 'api_key', None), snap['conexao'].webhook_secret, snap['conexao'].nome_instancia,
        )
    ):
        return _concluir(registro, EnvioTicketWhatsApp.Estado.INCERTO, 'resposta_nao_confirmada', http_status=502)
    return _concluir(registro, EnvioTicketWhatsApp.Estado.ACEITO, 'aceito_pelo_servico', id_provedor=identifier)
