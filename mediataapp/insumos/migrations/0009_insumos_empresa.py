from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('insumos', '0008_expandir_unidades_medida'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='insumos',
            name='empresa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='insumos', to='core.empresa'),
        ),
        migrations.AlterField(
            model_name='insumos', name='codigo', field=models.CharField(blank=True, max_length=9),
        ),
        migrations.AddConstraint(
            model_name='insumos',
            constraint=models.UniqueConstraint(fields=('empresa', 'codigo'), name='insumos_empresa_codigo_uniq'),
        ),
    ]
