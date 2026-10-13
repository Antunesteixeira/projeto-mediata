import re

from django.core.exceptions import ValidationError
from django.db.models.functions import Length
from django.utils import timezone


CODIGO_MENSAL = re.compile(r'([0-9]{2}(?:0[1-9]|1[0-2]))([0-9]{3})\Z')


def definir_codigo_ticket(codigo, using):
    """Reserve o código dentro da mesma transação que salva o ticket."""
    from .models import SequenciaTicket, Ticket

    codigo = str(codigo) if codigo is not None else ''
    automatico = not codigo.strip()
    manual = CODIGO_MENSAL.fullmatch(codigo)
    if not automatico and manual is None:
        return codigo

    prefixo = timezone.localdate().strftime('%y%m') if automatico else manual.group(1)
    sequencias = SequenciaTicket.objects.using(using)
    sequencias.get_or_create(prefixo=prefixo)
    sequencia = sequencias.select_for_update().get(prefixo=prefixo)

    # Inclui códigos anteriores à migração ou importados sem passar por save().
    maior_codigo = Ticket.objects.using(using).annotate(
        tamanho_codigo=Length('ticket'),
    ).filter(
        tamanho_codigo=7, ticket__regex=rf'^{prefixo}[0-9]{{3}}$',
    ).order_by('-ticket').values_list('ticket', flat=True).first()
    maior_existente = int(maior_codigo[-3:]) if maior_codigo else 0
    ultimo_numero = max(sequencia.ultimo_numero, maior_existente)

    if automatico:
        if ultimo_numero >= 999:
            raise ValidationError(
                'A sequência de tickets deste mês atingiu o limite de 999. '
                'Informe um código único ou procure o responsável pela operação.'
            )
        ultimo_numero += 1
        codigo = f'{prefixo}{ultimo_numero:03d}'
    else:
        ultimo_numero = max(ultimo_numero, int(manual.group(2)))

    if sequencia.ultimo_numero != ultimo_numero:
        sequencia.ultimo_numero = ultimo_numero
        sequencia.save(using=using, update_fields=['ultimo_numero'])
    return codigo
