from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('clientes', '0001_initial'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='empresa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='clientes', to='core.empresa'),
        ),
        migrations.AlterField(
            model_name='cliente', name='cpf_cnpj', field=models.CharField(max_length=18, verbose_name='CPF / CNPJ'),
        ),
        migrations.AddConstraint(
            model_name='cliente',
            constraint=models.UniqueConstraint(fields=('empresa', 'cpf_cnpj'), name='clientes_empresa_cpf_cnpj_uniq'),
        ),
    ]
