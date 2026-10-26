from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.state import ProjectState
from django.test import TestCase
from django.urls import reverse


EXPECTED_GROUP_PERMISSIONS = {
    'gerente': {'criar_ticket', 'ver_ticket', 'criar_insumo', 'criar_usuarios', 'ver_usuarios'},
    'operador': {'criar_ticket', 'ver_ticket'},
    'cliente': {'criar_ticket', 'ver_ticket'},
    'colaborador': {'ver_ticket'},
    'assinante': {'criar_ticket', 'ver_ticket'},
}
LEGACY_GROUP_PERMISSIONS = {
    **EXPECTED_GROUP_PERMISSIONS,
    'operador': {'criar_ticket', 'ver_ticket', 'criar_insumo'},
}
MIGRATION_MODULE = 'usuarios.migrations.0002_garantir_grupos_de_acesso'


class GruposDeAcessoTests(TestCase):
    def user_content_type(self):
        return ContentType.objects.get(
            app_label=User._meta.app_label, model=User._meta.model_name,
        )

    def run_forward(self):
        migration = import_module(MIGRATION_MODULE)
        historical_apps = ProjectState.from_apps(apps).apps
        # RunPython só altera dados; não inicia um contexto de DDL dentro
        # da transação do TestCase, permitindo também executar em SQLite.
        migration.garantir_grupos_de_acesso(historical_apps, connection.schema_editor())

    def assert_expected_groups_and_permissions(self, *, legacy=False):
        expected_groups = LEGACY_GROUP_PERMISSIONS if legacy else EXPECTED_GROUP_PERMISSIONS
        self.assertEqual(
            set(Group.objects.filter(name__in=EXPECTED_GROUP_PERMISSIONS).values_list('name', flat=True)),
            set(EXPECTED_GROUP_PERMISSIONS),
        )
        content_type = self.user_content_type()
        known_permissions = set().union(*EXPECTED_GROUP_PERMISSIONS.values())
        for name, expected_permissions in expected_groups.items():
            with self.subTest(group=name):
                group = Group.objects.get(name=name)
                assigned = set(group.permissions.filter(
                    content_type=content_type, codename__in=known_permissions,
                ).values_list('codename', flat=True))
                self.assertEqual(assigned, expected_permissions)

    def access_snapshot(self):
        return {
            'groups': dict(Group.objects.values_list('name', 'pk')),
            'permissions': list(Permission.objects.order_by('pk').values(
                'id', 'content_type_id', 'codename', 'name',
            )),
            'group_permissions': list(Group.permissions.through.objects.order_by(
                'group_id', 'permission_id',
            ).values_list('group_id', 'permission_id')),
            'user_groups': list(User.groups.through.objects.order_by(
                'user_id', 'group_id',
            ).values_list('user_id', 'group_id')),
            'user_permissions': list(User.user_permissions.through.objects.order_by(
                'user_id', 'permission_id',
            ).values_list('user_id', 'permission_id')),
        }

    def manager_client(self):
        manager = User.objects.create_superuser(
            username='admin_grupos_fixture', email='admin-grupos@example.invalid', password=None,
        )
        # O grupo deve existir após migrate, sem ser criado por assign_role.
        manager.groups.add(Group.objects.get(name='gerente'))
        self.client.force_login(manager)
        return manager

    def test_all_five_groups_and_role_permissions_exist_after_migrate(self):
        self.assert_expected_groups_and_permissions()

    def test_registration_dropdown_contains_all_five_groups(self):
        self.manager_client()
        response = self.client.get(reverse('registrar-usuarios'))
        self.assertEqual(response.status_code, 200)
        available = set(response.context['form'].fields['group'].queryset.values_list('name', flat=True))
        self.assertTrue(set(EXPECTED_GROUP_PERMISSIONS).issubset(available))
        for name in EXPECTED_GROUP_PERMISSIONS:
            with self.subTest(group=name):
                group = Group.objects.get(name=name)
                self.assertInHTML(
                    f'<option value="{group.pk}">{name}</option>', response.content.decode(),
                )

    def test_edit_dropdown_contains_all_five_groups_and_preserves_current_selection(self):
        manager = self.manager_client()
        response = self.client.get(reverse('editar-usuario', kwargs={'user_id': manager.pk}))
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        available = set(form.fields['groups'].queryset.values_list('name', flat=True))
        self.assertTrue(set(EXPECTED_GROUP_PERMISSIONS).issubset(available))
        self.assertEqual(str(form['groups'].value()), str(Group.objects.get(name='gerente').pk))
        for name in EXPECTED_GROUP_PERMISSIONS:
            with self.subTest(group=name):
                group = Group.objects.get(name=name)
                selected = ' selected' if str(form['groups'].value()) == str(group.pk) else ''
                self.assertInHTML(
                    f'<option value="{group.pk}"{selected}>{name}</option>', response.content.decode(),
                )

    def test_user_list_group_filter_contains_existing_and_custom_groups(self):
        manager = self.manager_client()
        custom_group = Group.objects.create(name='grupo_extra_fixture')
        member = User.objects.create_user(username='operador_listagem_fixture')
        member.groups.add(Group.objects.get(name='operador'))
        before = self.access_snapshot()

        response = self.client.get(reverse('index-usuarios'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, manager.username)
        self.assertContains(response, member.username)
        names = [group.name for group in response.context['grupos']]
        expected = set(EXPECTED_GROUP_PERMISSIONS) | {custom_group.name}
        self.assertTrue(expected.issubset(names))
        self.assertEqual(names, sorted(names))
        self.assertContains(response, 'id="filtro-grupo"')
        self.assertInHTML(
            '<option value="">Todos os Grupos</option>', response.content.decode(),
        )
        for name in expected:
            with self.subTest(group=name):
                self.assertInHTML(
                    f'<option value="{name}">{name}</option>', response.content.decode(),
                )
        self.assertEqual(self.access_snapshot(), before)

    def test_forward_recovers_previous_groups_when_only_subscriber_group_remains(self):
        subscriber_group = Group.objects.get(name='assinante')
        preserved_permission_ids = dict(subscriber_group.permissions.values_list('codename', 'pk'))
        custom_group = Group.objects.create(name='financeiro_personalizado_fixture')
        member = User.objects.create_user(username='membro_legado_fixture')
        member.groups.add(subscriber_group, custom_group)
        custom_permission = Permission.objects.create(
            content_type=self.user_content_type(), codename='exportar_personalizado_fixture',
            name='Exportação personalizada fictícia',
        )
        custom_group.permissions.add(custom_permission)
        subscriber_group.permissions.add(custom_permission)
        original_ids = {'assinante': subscriber_group.pk, custom_group.name: custom_group.pk}
        original_memberships = set(member.groups.values_list('pk', flat=True))
        Group.objects.filter(name__in=set(EXPECTED_GROUP_PERMISSIONS) - {'assinante'}).delete()
        Permission.objects.filter(
            content_type=self.user_content_type(),
            codename__in=('criar_insumo', 'criar_usuarios', 'ver_usuarios'),
        ).delete()

        self.run_forward()

        self.assert_expected_groups_and_permissions(legacy=True)
        for name, pk in original_ids.items():
            self.assertEqual(Group.objects.get(name=name).pk, pk)
        self.assertEqual(set(member.groups.values_list('pk', flat=True)), original_memberships)
        for group in (subscriber_group, custom_group):
            self.assertTrue(group.permissions.filter(pk=custom_permission.pk).exists())
        for codename, pk in preserved_permission_ids.items():
            self.assertTrue(subscriber_group.permissions.filter(pk=pk, codename=codename).exists())

    def test_repeated_forward_preserves_ids_memberships_and_custom_permissions(self):
        members = {}
        for name in EXPECTED_GROUP_PERMISSIONS:
            member = User.objects.create_user(username=f'membro_{name}_fixture')
            member.groups.add(Group.objects.get(name=name))
            members[name] = member
        custom_group = Group.objects.create(name='equipe_customizada_fixture')
        extra_permission = Permission.objects.create(
            content_type=self.user_content_type(), codename='aprovar_personalizado_fixture',
            name='Aprovação personalizada fictícia',
        )
        custom_group.permissions.add(extra_permission)
        members['gerente'].groups.add(custom_group)
        members['assinante'].user_permissions.add(extra_permission)
        for name in ('gerente', 'assinante'):
            Group.objects.get(name=name).permissions.add(extra_permission)
        existing_permission = Permission.objects.get(
            content_type=self.user_content_type(), codename='criar_ticket',
        )
        existing_permission.name = 'Nome personalizado da permissão existente'
        existing_permission.save(update_fields=['name'])
        # A 0002 representa a política histórica; a 0005 reduz os acessos atuais.
        self.run_forward()
        before = self.access_snapshot()

        self.run_forward()
        self.run_forward()

        self.assertEqual(self.access_snapshot(), before)
        self.assert_expected_groups_and_permissions(legacy=True)

    def test_reverse_keeps_groups_permissions_and_user_memberships(self):
        member = User.objects.create_user(username='membro_reversao_fixture')
        member.groups.add(Group.objects.get(name='assinante'), Group.objects.get(name='gerente'))
        before = self.access_snapshot()
        migration = import_module(MIGRATION_MODULE)
        historical_apps = ProjectState.from_apps(apps).apps
        for operation in reversed(migration.Migration.operations):
            operation.reverse_code(historical_apps, connection.schema_editor())
        self.assertEqual(self.access_snapshot(), before)
