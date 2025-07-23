from django import forms
from .models import Ticket

class TicketForm(forms.ModelForm):
    data_finalizar = forms.DateField(
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control',
                'placeholder': 'Data de finalização'
            }
        ),
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],
        required=False
    )

    class Meta:
        model = Ticket
        fields = [
            'ticket',
            'status',
            'emergencial',
            'valor_material',
            'valor_mao_obra',
            'valor_custo',
            'valor_faturamento',
            'data_finalizar',
            'descricao'
        ]

        labels = {
            'ticket': 'Número do Ticket',
            'status': 'Situação',
            'valor_material': 'Custo do Material',
            'valor_custo': 'Custo com Material',
            'valor_mao_obra': 'Custo com Mão de Obra',
            'valor_faturamento': 'Valor a Faturar',
            'data_finalizar': 'Previsão de Finalização',
            'descricao': 'Descrição do Serviço'
        }

        widgets = {
            'ticket': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 1234'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
            'emergencial': forms.HiddenInput(),
            'valor_mao_obra': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: R$ 150,00'
            }),
            'valor_material': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: R$ 100,00'
            }),
            'valor_custo': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: R$ 80,00'
            }),
            'valor_faturamento': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: R$ 230,00'
            }),
            'descricao': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Descreva o problema ou serviço executado...'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Esconde o campo emergencial para usuários não superuser
        if not self.instance.pk and self.user and not self.user.is_superuser:
            self.fields['emergencial'].widget = forms.HiddenInput()
            self.fields['emergencial'].required = False
