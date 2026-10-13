from django.conf import settings
from django.db import migrations


def criar_grupo_assinante(apps, schema_editor):
    database = schema_editor.connection.alias
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    user_app, user_model = settings.AUTH_USER_MODEL.split('.')

    content_type, _ = ContentType.objects.using(database).get_or_create(
        app_label=user_app,
        model=user_model.lower(),
    )
    group, _ = Group.objects.using(database).get_or_create(name='assinante')
    permissions = []
    for codename, name in (
        ('criar_ticket', 'Criar Ticket'),
        ('ver_ticket', 'Ver Ticket'),
    ):
        permission, _ = Permission.objects.using(database).get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={'name': name},
        )
        permissions.append(permission)
    group.permissions.add(*permissions)


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        # Preserve o grupo e seus usuários caso esta migração seja revertida.
        migrations.RunPython(criar_grupo_assinante, migrations.RunPython.noop),
    ]
