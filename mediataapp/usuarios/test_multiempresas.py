from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from rolepermissions.roles import assign_role

from colaborador.models import Colaborador
from tickets.models import Ticket
from .models import UsuarioEmpresa
from .test_helpers import criar_empresa, vincular_usuario


class UsuariosMultiempresaTests(TestCase):
    password = 'Empresa-Fixture-Password-41!'

    @classmethod
    def setUpTestData(cls):
        cls.company_a = criar_empresa()
        cls.company_b = criar_empresa('Empresa fictícia B', '00.000.000/0000-02')
        cls.manager_a = User.objects.create_user(username='gerente_equipe_a')
        cls.operator_a = User.objects.create_user(username='operador_equipe_a')
        cls.manager_b = User.objects.create_user(username='gerente_equipe_b')
        cls.operator_b = User.objects.create_user(username='operador_equipe_b')
        for user, role, company in (
            (cls.manager_a, 'gerente', cls.company_a),
            (cls.operator_a, 'operador', cls.company_a),
            (cls.manager_b, 'gerente', cls.company_b),
            (cls.operator_b, 'operador', cls.company_b),
        ):
            assign_role(user, role)
            vincular_usuario(user, company)
        cls.subscriber = User.objects.create_user(username='assinante_independente_equipe')
        assign_role(cls.subscriber, 'assinante')
        cls.administrator = User.objects.create_superuser(
            username='admin_empresas', email='admin@example.invalid', password=cls.password,
        )

    def setUp(self):
        self.client.force_login(self.manager_a)

    def snapshot(self):
        models = (
            User, UsuarioEmpresa, User.groups.through, User.user_permissions.through,
            Colaborador, Ticket,
        )
        return {
            model._meta.label_lower: list(model.objects.order_by('pk').values())
            for model in models
        }

    def creation_data(self, **changes):
        data = {
            'username': 'novo_operador_empresa', 'first_name': 'Novo operador',
            'last_name': '', 'email': 'novo@example.invalid',
            'password1': self.password, 'password2': self.password,
            'group': Group.objects.get(name='operador').pk, 'empresa': self.company_a.pk,
        }
        data.update(changes)
        return data

    def edit_data(self, user, **changes):
        group = user.groups.first()
        data = {
            'username': user.username, 'first_name': 'Nome atualizado',
            'last_name': '', 'email': 'atualizado@example.invalid',
            'groups': group.pk if group else Group.objects.get(name='operador').pk,
            'is_active': 'on', 'empresa': self.company_a.pk,
        }
        data.update(changes)
        return data

    def assert_successful_post(self, response):
        self.assertEqual(
            response.status_code, 302,
            response.context['form'].errors if response.status_code == 200 else None,
        )

    def test_manager_lists_only_team_and_cannot_read_or_edit_foreign_users(self):
        response = self.client.get(reverse('index-usuarios'))
        self.assertEqual(response.status_code, 200)
        for user in (self.manager_a, self.operator_a):
            self.assertContains(response, user.username)
        for user in (self.manager_b, self.operator_b, self.subscriber, self.administrator):
            self.assertNotContains(response, user.username)
            before = self.snapshot()
            self.assertEqual(self.client.get(reverse('perfil-usuario', kwargs={'id': user.pk})).status_code, 404)
            url = reverse('editar-usuario', kwargs={'user_id': user.pk})
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.edit_data(
                user, groups=Group.objects.get(name='operador').pk,
            )).status_code, 404)
            self.assertEqual(self.snapshot(), before)

    def test_manager_creates_staff_only_in_own_company_despite_forged_company_and_flags(self):
        response = self.client.post(reverse('registrar-usuarios'), self.creation_data(
            empresa=self.company_b.pk, is_staff='on', is_superuser='on',
        ))
        self.assert_successful_post(response)
        created = User.objects.get(username='novo_operador_empresa')
        self.assertEqual(created.vinculo_empresa.empresa_id, self.company_a.pk)
        self.assertEqual(list(created.groups.values_list('name', flat=True)), ['operador'])
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertEqual(self.operator_b.vinculo_empresa.empresa_id, self.company_b.pk)

    def test_manager_cannot_create_independent_subscriber_from_company_registration(self):
        response = self.client.get(reverse('registrar-usuarios'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].fields['group'].queryset.filter(name='assinante').exists())
        before = self.snapshot()
        response = self.client.post(reverse('registrar-usuarios'), self.creation_data(
            group=Group.objects.get(name='assinante').pk,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertIn('group', response.context['form'].errors)
        self.assertEqual(self.snapshot(), before)

    def test_manager_can_edit_team_member_but_cannot_move_them_to_foreign_company(self):
        response = self.client.post(
            reverse('editar-usuario', kwargs={'user_id': self.operator_a.pk}),
            self.edit_data(self.operator_a, empresa=self.company_b.pk, is_staff='on', is_superuser='on'),
        )
        self.assert_successful_post(response)
        self.operator_a.refresh_from_db()
        self.assertEqual(self.operator_a.first_name, 'Nome atualizado')
        self.assertEqual(self.operator_a.vinculo_empresa.empresa_id, self.company_a.pk)
        self.assertFalse(self.operator_a.is_staff)
        self.assertFalse(self.operator_a.is_superuser)

    def test_operator_can_edit_own_basic_profile_without_escalating_or_moving_company(self):
        self.client.force_login(self.operator_a)
        permissions_before = set(self.operator_a.user_permissions.values_list('pk', flat=True))
        profiles_before = list(UsuarioEmpresa.objects.order_by('pk').values())
        response = self.client.post(
            reverse('editar-usuario', kwargs={'user_id': self.operator_a.pk}),
            self.edit_data(
                self.operator_a, groups=Group.objects.get(name='gerente').pk,
                empresa=self.company_b.pk, is_active='', is_staff='on', is_superuser='on',
            ),
        )
        self.assert_successful_post(response)
        self.operator_a.refresh_from_db()
        self.assertEqual(self.operator_a.first_name, 'Nome atualizado')
        self.assertEqual(list(self.operator_a.groups.values_list('name', flat=True)), ['operador'])
        self.assertTrue(self.operator_a.is_active)
        self.assertFalse(self.operator_a.is_staff)
        self.assertFalse(self.operator_a.is_superuser)
        self.assertEqual(set(self.operator_a.user_permissions.values_list('pk', flat=True)), permissions_before)
        self.assertEqual(list(UsuarioEmpresa.objects.order_by('pk').values()), profiles_before)
        for name in ('index-usuarios', 'registrar-usuarios'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertEqual(self.client.get(reverse(
            'editar-usuario', kwargs={'user_id': self.manager_a.pk},
        )).status_code, 403)

    def test_company_views_are_scoped_and_only_superuser_can_create_companies(self):
        response = self.client.get(reverse('empresa_lista'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.company_a.nome_fantasia)
        self.assertNotContains(response, self.company_b.nome_fantasia)
        for name in ('empresa_perfil', 'empresa_editar'):
            self.assertEqual(self.client.get(reverse(name, kwargs={'pk': self.company_b.pk})).status_code, 404)
        self.assertEqual(self.client.get(reverse('empresa_cadastrar')).status_code, 403)
        self.client.force_login(self.operator_a)
        self.assertEqual(self.client.get(reverse('empresa_editar', kwargs={'pk': self.company_a.pk})).status_code, 403)
        self.client.force_login(self.administrator)
        self.assertEqual(self.client.get(reverse('empresa_cadastrar')).status_code, 200)
        response = self.client.get(reverse('empresa_lista'))
        self.assertContains(response, self.company_a.nome_fantasia)
        self.assertContains(response, self.company_b.nome_fantasia)

    def test_superuser_can_create_internal_user_with_chosen_company(self):
        self.client.force_login(self.administrator)
        response = self.client.post(reverse('registrar-usuarios'), self.creation_data(empresa=self.company_b.pk))
        self.assert_successful_post(response)
        created = User.objects.get(username='novo_operador_empresa')
        self.assertEqual(created.vinculo_empresa.empresa_id, self.company_b.pk)

    def test_superuser_subscriber_registration_keeps_account_independent(self):
        self.client.force_login(self.administrator)
        response = self.client.post(reverse('registrar-usuarios'), self.creation_data(
            group=Group.objects.get(name='assinante').pk, empresa=self.company_b.pk,
        ))
        self.assert_successful_post(response)
        created = User.objects.get(username='novo_operador_empresa')
        self.assertEqual(list(created.groups.values_list('name', flat=True)), ['assinante'])
        self.assertFalse(UsuarioEmpresa.objects.filter(usuario=created).exists())

    def test_missing_or_inactive_company_blocks_operational_team_management(self):
        missing = User.objects.create_user(username='gerente_sem_vinculo')
        assign_role(missing, 'gerente')
        self.company_a.ativo = False
        self.company_a.save(update_fields=['ativo'])
        for user in (missing, self.manager_a):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                before = self.snapshot()
                for name in ('index-usuarios', 'registrar-usuarios'):
                    self.assertEqual(self.client.get(reverse(name)).status_code, 403)
                    self.assertEqual(self.client.post(reverse(name), self.creation_data()).status_code, 403)
                self.assertEqual(self.snapshot(), before)

    def linked_contractor(self):
        contractor = Colaborador.objects.create(
            user=self.operator_a, empresa=self.company_a, nome_completo='Colaborador vinculado à empresa A',
        )
        ticket = Ticket.objects.create(
            ticket='LINKCOL001', empresa=self.company_a, usuario=self.operator_a,
            colaborador=contractor, descricao='Ticket histórico do colaborador',
        )
        return contractor, ticket

    def test_linked_contractor_prevents_company_move_without_reassigning_historical_records(self):
        self.linked_contractor()
        self.client.force_login(self.administrator)
        before = self.snapshot()
        response = self.client.post(
            reverse('editar-usuario', kwargs={'user_id': self.operator_a.pk}),
            self.edit_data(self.operator_a, empresa=self.company_b.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('empresa', response.context['form'].errors)
        self.assertEqual(self.snapshot(), before)

    def test_linked_contractor_prevents_conversion_to_independent_subscriber(self):
        self.linked_contractor()
        self.client.force_login(self.administrator)
        before = self.snapshot()
        response = self.client.post(
            reverse('editar-usuario', kwargs={'user_id': self.operator_a.pk}),
            self.edit_data(self.operator_a, groups=Group.objects.get(name='assinante').pk, empresa=''),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('groups', response.context['form'].errors)
        self.assertEqual(self.snapshot(), before)

    def test_basic_edit_of_linked_contractor_user_keeps_company_and_ticket_relationships(self):
        contractor, ticket = self.linked_contractor()
        self.client.force_login(self.administrator)
        response = self.client.post(
            reverse('editar-usuario', kwargs={'user_id': self.operator_a.pk}), self.edit_data(self.operator_a),
        )
        self.assert_successful_post(response)
        self.operator_a.refresh_from_db()
        contractor.refresh_from_db()
        ticket.refresh_from_db()
        self.assertEqual(self.operator_a.first_name, 'Nome atualizado')
        self.assertEqual(self.operator_a.vinculo_empresa.empresa_id, self.company_a.pk)
        self.assertEqual(contractor.empresa_id, self.company_a.pk)
        self.assertEqual(ticket.empresa_id, self.company_a.pk)
        self.assertEqual(ticket.colaborador_id, contractor.pk)
