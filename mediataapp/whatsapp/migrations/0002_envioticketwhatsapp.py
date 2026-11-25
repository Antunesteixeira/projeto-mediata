import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('whatsapp', '0001_initial'),
        ('tickets', '0038_pagamentos_datas_financeiras'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EnvioTicketWhatsApp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('idempotencia', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('ticket_numero', models.CharField(max_length=10)),
                ('colaborador_nome', models.CharField(max_length=200)),
                ('telefone_mascarado', models.CharField(max_length=40)),
                ('fingerprint', models.CharField(db_index=True, editable=False, max_length=64)),
                ('estado', models.CharField(choices=[('processando', 'Processando'), ('aceito', 'Aceito pelo serviço'), ('falhou', 'Não enviado'), ('incerto', 'Resultado não confirmado')], default='processando', max_length=12)),
                ('codigo_resultado', models.CharField(blank=True, default='', max_length=40)),
                ('id_provedor', models.CharField(blank=True, default='', max_length=128)),
                ('criado_em', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('finalizado_em', models.DateTimeField(blank=True, null=True)),
                ('colaborador', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='envios_ticket_whatsapp', to='colaborador.colaborador')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='envios_ticket_whatsapp', to='core.empresa')),
                ('ticket', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='envios_whatsapp', to='tickets.ticket')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='envios_ticket_whatsapp', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Envio de ticket por WhatsApp',
                'verbose_name_plural': 'Envios de tickets por WhatsApp',
                'ordering': ['-criado_em', '-pk'],
            },
        ),
    ]
