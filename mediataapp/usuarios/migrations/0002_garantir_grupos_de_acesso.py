from django.conf import settings
from django.db import migrations


GROUP_PERMISSIONS = {
    'gerente': ('criar_ticket', 'ver_ticket', 'criar_insumo', 'criar_usuarios', 'ver_usuarios'),
    'operador': ('criar_ticket', 'ver_ticket', 'criar_insumo'),
    'cliente': ('criar_ticket', 'ver_ticket'),
    'colaborador': ('ver_ticket',),
    'assinante': ('criar_ticket', 'ver_ticket'),
}

PERMISSION_NAMES = {
    'criar_ticket': 'Criar Ticket',
    'ver_ticket': 'Ver Ticket',
    'criar_insumo': 'Criar Insumo',
    'criar_usuarios': 'Criar Usuarios',
    'ver_usuarios': 'Ver Usuarios',
}


def garantir_grupos_de_acesso(apps, schema_editor):
    database = schema_editor.connection.alias
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    user_app, user_model = settings.AUTH_USER_MODEL.split('.')

    content_type, _ = ContentType.objects.using(database).get_or_create(
        app_label=user_app,
        model=user_model.lower(),
    )
    permissions = {}
    for codename, name in PERMISSION_NAMES.items():
        permission, _ = Permission.objects.using(database).get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={'name': name},
        )
        permissions[codename] = permission

    for group_name, permission_names in GROUP_PERMISSIONS.items():
        group, _ = Group.objects.using(database).get_or_create(name=group_name)
        group.permissions.add(*(permissions[name] for name in permission_names))


class Migration(migrations.Migration):
    dependencies = [
        ('usuarios', '0001_criar_grupo_assinante'),
    ]

    operations = [
        # Preserve os grupos, suas permissões e vínculos em caso de reversão.
        migrations.RunPython(garantir_grupos_de_acesso, migrations.RunPython.noop),
    ]
