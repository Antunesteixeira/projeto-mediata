import secrets
import uuid

from django.db import models
from django.conf import settings


def gerar_webhook_secret():
    return secrets.token_hex(32)


class ConexaoWhatsApp(models.Model):
    class Estado(models.TextChoices):
        DESCONECTADO = 'desconectado', 'Desconectado'
        CONECTANDO = 'conectando', 'Conectando'
        AGUARDANDO_QR = 'aguardando_qr', 'Aguardando leitura do QR Code'
        CONECTADO = 'conectado', 'Conectado'
        ERRO = 'erro', 'Não foi possível consultar a conexão'

    empresa = models.OneToOneField(
        'core.Empresa', on_delete=models.PROTECT, related_name='conexao_whatsapp',
    )
    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.DESCONECTADO)
    instancia_criada = models.BooleanField(default=False, editable=False)
    webhook_secret = models.CharField(max_length=64, default=gerar_webhook_secret, editable=False)
    operacao_id = models.UUIDField(null=True, blank=True, editable=False)
    operacao_iniciada_em = models.DateTimeField(null=True, blank=True, editable=False)
    ultimo_evento_em = models.DateTimeField(null=True, blank=True, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Conexão WhatsApp'
        verbose_name_plural = 'Conexões WhatsApp'

    @property
    def nome_instancia(self):
        return f'mediata-{self.identificador.hex}'

    def __str__(self):
        return f'Conexão WhatsApp da empresa {self.empresa_id}'


class EnvioTicketWhatsApp(models.Model):
    class Estado(models.TextChoices):
        PROCESSANDO = 'processando', 'Processando'
        ACEITO = 'aceito', 'Aceito pelo serviço'
        FALHOU = 'falhou', 'Não enviado'
        INCERTO = 'incerto', 'Resultado não confirmado'

    idempotencia = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    empresa = models.ForeignKey(
        'core.Empresa', on_delete=models.PROTECT, related_name='envios_ticket_whatsapp',
    )
    ticket = models.ForeignKey(
        'tickets.Ticket', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='envios_whatsapp',
    )
    colaborador = models.ForeignKey(
        'colaborador.Colaborador', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='envios_ticket_whatsapp',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='envios_ticket_whatsapp',
    )
    ticket_numero = models.CharField(max_length=10)
    colaborador_nome = models.CharField(max_length=200)
    telefone_mascarado = models.CharField(max_length=40)
    fingerprint = models.CharField(max_length=64, db_index=True, editable=False)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PROCESSANDO)
    codigo_resultado = models.CharField(max_length=40, blank=True, default='')
    id_provedor = models.CharField(max_length=128, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Envio de ticket por WhatsApp'
        verbose_name_plural = 'Envios de tickets por WhatsApp'
        ordering = ['-criado_em', '-pk']

    def __str__(self):
        return f'Ticket {self.ticket_numero} — {self.get_estado_display()}'
