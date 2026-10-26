from django.conf import settings
from django.db import migrations


def restringir_permissoes_operador(apps, schema_editor):
    database = schema_editor.connection.alias
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    user_app, user_model = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(user_app, user_model)
    permissions = list(Permission.objects.using(database).filter(
        content_type__app_label=user_app,
        content_type__model=user_model.lower(),
        codename__in=('criar_insumo', 'criar_usuarios', 'ver_usuarios'),
    ).values_list('pk', flat=True))
    groups = Group.objects.using(database).filter(name='operador')
    Group.permissions.through.objects.using(database).filter(
        group_id__in=groups.values('pk'), permission_id__in=permissions,
    ).delete()
    operators = User.objects.using(database).filter(
        groups__name='operador', is_superuser=False,
    ).exclude(groups__name='gerente')
    # assign_role também grava permissões diretamente no usuário.
    relation = User._meta.get_field('user_permissions')
    relation.remote_field.through.objects.using(database).filter(**{
        f'{relation.m2m_field_name()}_id__in': operators.values('pk'),
        'permission_id__in': permissions,
    }).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('usuarios', '0004_vincular_dados_legados'),
    ]

    operations = [
        # Reverter o código não deve restaurar privilégios administrativos.
        migrations.RunPython(restringir_permissoes_operador, migrations.RunPython.noop),
    ]
