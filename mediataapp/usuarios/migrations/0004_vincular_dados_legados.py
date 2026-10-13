from django.conf import settings
from django.db import migrations
from django.db.models import F


def vincular_dados_legados(apps, schema_editor):
    database = schema_editor.connection.alias
    Empresa = apps.get_model('core', 'Empresa')
    UsuarioEmpresa = apps.get_model('usuarios', 'UsuarioEmpresa')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    legacy = Empresa.objects.using(database).order_by('pk').first()
    if legacy is None:
        return

    usuarios = User.objects.using(database).filter(is_superuser=False).exclude(
        groups__name='assinante',
    ).distinct()
    for user in usuarios.iterator():
        UsuarioEmpresa.objects.using(database).get_or_create(
            usuario_id=user.pk, defaults={'empresa_id': legacy.pk},
        )

    for app_label, model_name in (
        ('tickets', 'Ticket'),
        ('clientes', 'Cliente'),
        ('colaborador', 'Colaborador'),
        ('insumos', 'Insumos'),
    ):
        model = apps.get_model(app_label, model_name)
        model.objects.using(database).filter(empresa_id__isnull=True).update(empresa_id=legacy.pk)

    Ticket = apps.get_model('tickets', 'Ticket')
    autores_internos = User.objects.using(database).exclude(groups__name='assinante').values_list('pk', flat=True)
    Ticket.objects.using(database).filter(
        assumido_por_id__isnull=True, usuario_id__in=autores_internos,
    ).update(assumido_por_id=F('usuario_id'))

    Colaborador = apps.get_model('colaborador', 'Colaborador')
    for colaborador in Colaborador.objects.using(database).exclude(user_id=None).iterator():
        user = User.objects.using(database).filter(pk=colaborador.user_id, is_superuser=False).exclude(
            groups__name='assinante',
        ).first()
        if user is not None:
            UsuarioEmpresa.objects.using(database).get_or_create(
                usuario_id=user.pk, defaults={'empresa_id': colaborador.empresa_id},
            )


class Migration(migrations.Migration):
    dependencies = [
        ('usuarios', '0003_usuarioempresa'),
        ('tickets', '0037_ticket_empresa_e_assuncao'),
        ('clientes', '0002_cliente_empresa'),
        ('colaborador', '0007_colaborador_empresa'),
        ('insumos', '0009_insumos_empresa'),
    ]

    operations = [
        # Os vínculos existentes são preservados também em caso de reversão.
        migrations.RunPython(vincular_dados_legados, migrations.RunPython.noop),
    ]
