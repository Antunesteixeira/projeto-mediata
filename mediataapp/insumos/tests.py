from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rolepermissions.roles import assign_role
from unittest.mock import patch
from core.models import Empresa
from usuarios.models import UsuarioEmpresa

from .forms import InsumoForm
from .models import Insumos


class InsumoUnitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Empresa.objects.create(
            nome_fantasia='Empresa A insumos', razao_social='Empresa A de teste',
            cnpj='11.111.111/0001-11', email='empresa-a@example.com', telefone='(11) 1111-1111',
        )
        cls.foreign_company = Empresa.objects.create(
            nome_fantasia='Empresa B insumos', razao_social='Empresa B de teste',
            cnpj='22.222.222/0001-22', email='empresa-b@example.com', telefone='(22) 2222-2222',
        )
        cls.operator = User.objects.create_user(username='operador_insumos')
        assign_role(cls.operator, 'operador')
        UsuarioEmpresa.objects.create(usuario=cls.operator, empresa=cls.company)

    def form_data(self, unit):
        return {
            'insumo': f'Insumo de teste {unit}', 'tipo': 'M',
            'unidade': unit, 'valor_unit': '10.50', 'quant': '1',
        }

    def test_new_units_can_be_registered_and_loaded(self):
        for unit in ('SC25KG', 'M2/MES', 'M3XKM', 'PÇ', 'KW/H', 'pp.', 'PCT', 'SACO'):
            with self.subTest(unit=unit):
                form = InsumoForm(data=self.form_data(unit), actor=self.operator)
                self.assertTrue(form.is_valid(), form.errors)
                supply = form.save()
                supply.refresh_from_db()
                self.assertEqual(supply.unidade, unit)
                self.assertEqual(supply.empresa_id, self.company.pk)
                self.assertEqual(InsumoForm(instance=supply, actor=self.operator)['unidade'].value(), unit)

    def test_existing_units_keep_their_meaning_when_edited(self):
        for unit, name in (('PC', 'Peça'), ('SC', 'Saca'), ('ROLO', 'Rolo'), ('BALDE', 'Balde')):
            with self.subTest(unit=unit):
                supply = Insumos.objects.create(
                    insumo='Insumo existente', tipo='M', unidade=unit, empresa=self.company,
                )
                form = InsumoForm(data=self.form_data(unit), instance=supply, actor=self.operator)
                self.assertTrue(form.is_valid(), form.errors)
                form.save()
                supply.refresh_from_db()
                self.assertEqual(supply.unidade, unit)
                self.assertEqual(supply.get_unidade_display(), f'{name} ({unit})')

    def test_company_scope_protects_listing_foreign_ids_and_forged_company(self):
        own = Insumos.objects.create(insumo='Insumo da empresa A', tipo='M', empresa=self.company)
        foreign = Insumos.objects.create(insumo='Insumo da empresa B', tipo='M', empresa=self.foreign_company)
        self.client.force_login(self.operator)
        response = self.client.get(reverse('index-insumos'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context['insumos'].values_list('pk', flat=True)), {own.pk})
        self.assertNotContains(response, foreign.insumo)
        for method in ('get', 'post'):
            response = getattr(self.client, method)(reverse('editar-insumos', kwargs={'id': foreign.pk}))
            self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse('deletar-insumos', kwargs={'id': foreign.pk}))
        self.assertEqual(response.status_code, 404)
        payload = {**self.form_data('UN'), 'empresa': str(self.foreign_company.pk)}
        response = self.client.post(reverse('index-insumos'), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Insumos.objects.get(insumo=payload['insumo']).empresa_id, self.company.pk)
        self.assertTrue(Insumos.objects.filter(pk=foreign.pk).exists())

    def test_read_only_roles_cannot_mutate_company_supplies(self):
        supply = Insumos.objects.create(insumo='Insumo protegido', tipo='M', empresa=self.company)
        for role in ('cliente', 'colaborador'):
            user = User.objects.create_user(username=f'{role}_insumos')
            assign_role(user, role)
            UsuarioEmpresa.objects.create(usuario=user, empresa=self.company)
            self.client.force_login(user)
            for name, kwargs in (
                ('index-insumos', {}), ('editar-insumos', {'id': supply.pk}),
                ('deletar-insumos', {'id': supply.pk}),
            ):
                with self.subTest(role=role, route=name):
                    response = self.client.post(reverse(name, kwargs=kwargs), self.form_data('UN'))
                    self.assertEqual(response.status_code, 403)
        self.assertTrue(Insumos.objects.filter(pk=supply.pk).exists())

    def test_supply_codes_are_independent_between_companies(self):
        for company in (self.company, self.foreign_company):
            with self.subTest(company=company.pk), patch.object(
                Insumos, '_generate_unique_codigo', return_value='INS0001',
            ):
                supply = Insumos.objects.create(insumo='Mesmo código em outra empresa', tipo='M', empresa=company)
                self.assertEqual(supply.codigo, 'INS0001')
        self.assertEqual(Insumos.objects.filter(codigo='INS0001').count(), 2)
