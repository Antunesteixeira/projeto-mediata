from django import forms
from .models import Ticket, Orcamento, Servico, Material, HistoricoTicket, ItemOrcamento

class TicketForm(forms.ModelForm):
    data_finalizar = forms.DateField(
    widget=forms.DateInput(
        attrs={
            'class': 'form-control',
            'type': 'date',
        },
        format='%Y-%m-%d'  # formato compatível com input type="date"
        )
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

class OrcamentoForm(forms.ModelForm):
    class Meta:
        model = Orcamento
        fields = [
            'orcamento',
            'descricao'
        ]
        labels = {
            'orcamento': 'Orçamento',
            'descricao': 'Descrição'
        }
        widgets = {
            'orcamento': forms.TextInput(attrs={'class': 'form-control'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class ServicoForm(forms.ModelForm):
    class Meta:
        model = Servico
        fields = [
            'servico', #entenda como insumo
            'valor_servico'
        ]
        labels = {
            'servico': 'insumo'
        }
        widgets = {
            'servico': forms.TextInput(attrs={'class': 'form-control'}),
            'valor_servico': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: R$ 230,00'
            }),
        }

class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = [
            'material',
            'valor_material'
        ]
        widgets = {
            'material': forms.TextInput(attrs={'class': 'form-control'}),
            'valor_material': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: R$ 250,00'
            }),
        }

class HistorcoTicketForm(forms.ModelForm):
    class Meta:
        model = HistoricoTicket
        fields = [
            'descricao_historico'
        ]
        widgets = {
            'descricao_historico': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class ItemOrcamentoForm(forms.ModelForm):
    class Meta:
        model = ItemOrcamento
        fields = [
            'item',
            'quant',
        ]
        widgets = {
            'item': forms.Select(attrs={
                'class': 'form-select'
            }),
            'quant': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 5'
            }),
        }