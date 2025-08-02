from django import forms
from .models import Insumos

class InsumoForm(forms.ModelForm):
    class Meta:
        model = Insumos
        fields = [
            'insumo',
            'tipo', 
            'valor_unit',
            'quant',
        ]

        labels = {
            'insumo': 'Insumo',
            'Tipo': 'Tipo',
            'valor_unit': 'Valor unitário',
            'quant': 'Quantidade'
        }

        widgets = {
            'insumo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Lâmpada 120w'
            }),
            'valor_unit': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 120'
            }),
            'quant': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 10'
            }),
            'tipo': forms.Select(attrs={
                'class': 'form-select'
            }),
        }