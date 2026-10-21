from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LancamentoManual',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operacao', models.CharField(choices=[('credito', 'Crédito'), ('debito', 'Débito')], max_length=7, verbose_name='Operação')),
                ('descricao', models.CharField(max_length=255, verbose_name='Descrição')),
                ('contraparte', models.CharField(blank=True, default='', max_length=255, verbose_name='Cliente/Favorecido')),
                ('valor', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Valor')),
                ('data_vencimento', models.DateField(db_index=True, verbose_name='Vencimento')),
                ('liquidado', models.BooleanField(default=False, verbose_name='Quitado')),
                ('data_quitacao', models.DateField(blank=True, null=True, verbose_name='Data da quitação')),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, verbose_name='Atualizado em')),
                ('criado_por', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Criado por')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lancamentos_financeiros_manuais', to='core.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Lançamento manual',
                'verbose_name_plural': 'Lançamentos manuais',
                'ordering': ['data_vencimento', 'id'],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('valor__gt', 0)), name='financeiro_manual_valor_positivo'),
                    models.CheckConstraint(condition=models.Q(models.Q(('data_quitacao__isnull', True), ('liquidado', False)), models.Q(('data_quitacao__isnull', False), ('liquidado', True)), _connector='OR'), name='financeiro_manual_quitacao_coerente'),
                ],
            },
        ),
    ]
