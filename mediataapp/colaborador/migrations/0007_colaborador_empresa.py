from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('colaborador', '0006_colaborador_user'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='colaborador',
            name='empresa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='colaboradores', to='core.empresa'),
        ),
        migrations.AlterField(
            model_name='colaborador', name='cpf', field=models.CharField(blank=True, max_length=14, null=True),
        ),
        migrations.AlterField(
            model_name='colaborador', name='cnpj', field=models.CharField(blank=True, max_length=18, null=True),
        ),
        migrations.AddConstraint(
            model_name='colaborador',
            constraint=models.UniqueConstraint(fields=('empresa', 'cpf'), name='colaborador_empresa_cpf_uniq'),
        ),
        migrations.AddConstraint(
            model_name='colaborador',
            constraint=models.UniqueConstraint(fields=('empresa', 'cnpj'), name='colaborador_empresa_cnpj_uniq'),
        ),
    ]
