from django.test import TestCase

from .forms import InsumoForm
from .models import Insumos


class InsumoUnitTests(TestCase):
    def form_data(self, unit):
        return {
            'insumo': f'Insumo de teste {unit}', 'tipo': 'M',
            'unidade': unit, 'valor_unit': '10.50', 'quant': '1',
        }

    def test_new_units_can_be_registered_and_loaded(self):
        for unit in ('SC25KG', 'M2/MES', 'M3XKM', 'PÇ', 'KW/H', 'pp.', 'PCT', 'SACO'):
            with self.subTest(unit=unit):
                form = InsumoForm(data=self.form_data(unit))
                self.assertTrue(form.is_valid(), form.errors)
                supply = form.save()
                supply.refresh_from_db()
                self.assertEqual(supply.unidade, unit)
                self.assertEqual(InsumoForm(instance=supply)['unidade'].value(), unit)

    def test_existing_units_keep_their_meaning_when_edited(self):
        for unit, name in (('PC', 'Peça'), ('SC', 'Saca'), ('ROLO', 'Rolo'), ('BALDE', 'Balde')):
            with self.subTest(unit=unit):
                supply = Insumos.objects.create(insumo='Insumo existente', tipo='M', unidade=unit)
                form = InsumoForm(data=self.form_data(unit), instance=supply)
                self.assertTrue(form.is_valid(), form.errors)
                form.save()
                supply.refresh_from_db()
                self.assertEqual(supply.unidade, unit)
                self.assertEqual(supply.get_unidade_display(), f'{name} ({unit})')
