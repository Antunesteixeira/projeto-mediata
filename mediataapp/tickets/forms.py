from django import forms
from .models import Ticket, Orcamento, Servico, Material, HistoricoTicket, ItemOrcamento, Pagamentos, Anexo, Recebimentos

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
            'data_finalizar',
            'descricao'
        ]

        labels = {
            'ticket': 'Número do Ticket',
            'status': 'Situação',
            'valor_material': 'Custo do Material',
            'valor_custo': 'Custo Total',
            'valor_mao_obra': 'Custo com Mão de Obra',
            'valor_faturamento': 'Valor a Faturar',
            'valor_equipamento': 'Custo com equipamento',
            'emergencial': 'Emergencial',
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
            'emergencial': forms.CheckboxInput(attrs={
                'class': 'form-check-input' # Classe do Bootstrap para checkboxes
            }),
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
            'valor_equipamento': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: R$ 250,00'
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

class PagamentoForm(forms.ModelForm):
    valor_pagamento = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 100.00',
            'step': '0.01'
        })
    )

    class Meta:
        model = Pagamentos
        fields = ['tipo', 'valor_pagamento', 'status_pagamento', 'data_pagamento']
        
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'status_pagamento': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'data_pagamento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial['valor_pagamento'] = self.instance.valor_pagamento

class AnexoForm(forms.ModelForm):
    class Meta:
        model = Anexo
        fields = ['arquivo', 'descricao_anexo']  # 'nome_arquivo' removido, pois será derivado do arquivo
        widgets = {
            'descricao_anexo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Descrição (opcional)'}),
            'arquivo': forms.FileInput(attrs={'class': 'form-control'}),
        }


class RecebimentosForm(forms.ModelForm):
    class Meta:
        model = Recebimentos
        exclude = ['razao_social', 'ticket_recebimento', 'comprovante_recebimento']  # ← exclui o campo FK
        widgets = {
            'data_emissao': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data_vencimento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'descricao_recebimento': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'recebimento_realizado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'data_recebimento_realizado': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
        labels = {
            #'razao_social': 'Razão Social',
            'numero_nota_fiscal': 'Número da Nota Fiscal',
            'serie_nota_fiscal': 'Série da Nota Fiscal',
            'data_emissao': 'Data de Emissão',
            'data_vencimento': 'Data de Vencimento',
            'valor_recebimento': 'Valor',
            'status_recebimento': 'Status',
            'descricao_recebimento': 'Descrição',
            'forma_pagamento': 'Forma de Pagamento',
            'tipo_pagamento': 'Tipo de Pagamento',
            #'comprovante_recebimento': 'Comprovante',
            'recebimento_realizado': 'Recebimento Realizado',
            'data_recebimento_realizado': 'Data do Recebimento'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Adiciona classe form-control a todos os campos que não são checkbox/radio
        for field_name, field in self.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
                field.widget.attrs.setdefault('class', 'form-control')
        # Define todos como não obrigatórios (ajuste conforme necessário)
        for field in self.fields.values():
            field.required = False
        # Exemplo: tornar valor_recebimento obrigatório
        # self.fields['valor_recebimento'].required = True