import re

from django.db import migrations, models


def iniciar_sequencias(apps, schema_editor):
    database = schema_editor.connection.alias
    Ticket = apps.get_model('tickets', 'Ticket')
    SequenciaTicket = apps.get_model('tickets', 'SequenciaTicket')
    pattern = re.compile(r'([0-9]{2}(?:0[1-9]|1[0-2]))([0-9]{3})\Z')
    maiores = {}
    for codigo in Ticket.objects.using(database).values_list('ticket', flat=True).iterator():
        match = pattern.fullmatch(codigo)
        if match:
            prefixo, numero = match.groups()
            maiores[prefixo] = max(maiores.get(prefixo, 0), int(numero))
    for prefixo, numero in maiores.items():
        sequencia, _ = SequenciaTicket.objects.using(database).get_or_create(prefixo=prefixo)
        if sequencia.ultimo_numero < numero:
            sequencia.ultimo_numero = numero
            sequencia.save(using=database, update_fields=['ultimo_numero'])


class Migration(migrations.Migration):
    dependencies = [('tickets', '0035_alter_recebimentos_forma_pagamento')]

    operations = [
        migrations.CreateModel(
            name='SequenciaTicket',
            fields=[
                ('prefixo', models.CharField(max_length=4, primary_key=True, serialize=False)),
                ('ultimo_numero', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'constraints': [models.CheckConstraint(
                    condition=models.Q(ultimo_numero__lte=999),
                    name='sequencia_ticket_limite_999',
                )],
            },
        ),
        migrations.RunPython(iniciar_sequencias, migrations.RunPython.noop),
    ]
