import uuid

import django.db.models.deletion
from django.db import migrations, models

import whatsapp.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [('core', '0001_initial')]

    operations = [
        migrations.CreateModel(
            name='ConexaoWhatsApp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identificador', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('estado', models.CharField(choices=[('desconectado', 'Desconectado'), ('conectando', 'Conectando'), ('aguardando_qr', 'Aguardando leitura do QR Code'), ('conectado', 'Conectado'), ('erro', 'Não foi possível consultar a conexão')], default='desconectado', max_length=20)),
                ('instancia_criada', models.BooleanField(default=False, editable=False)),
                ('webhook_secret', models.CharField(default=whatsapp.models.gerar_webhook_secret, editable=False, max_length=64)),
                ('operacao_id', models.UUIDField(blank=True, editable=False, null=True)),
                ('operacao_iniciada_em', models.DateTimeField(blank=True, editable=False, null=True)),
                ('ultimo_evento_em', models.DateTimeField(blank=True, editable=False, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('empresa', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='conexao_whatsapp', to='core.empresa')),
            ],
            options={'verbose_name': 'Conexão WhatsApp', 'verbose_name_plural': 'Conexões WhatsApp'},
        ),
    ]
