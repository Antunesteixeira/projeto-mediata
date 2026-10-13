from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('usuarios', '0002_garantir_grupos_de_acesso'),
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UsuarioEmpresa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='usuarios_vinculados', to='core.empresa')),
                ('usuario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='vinculo_empresa', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
