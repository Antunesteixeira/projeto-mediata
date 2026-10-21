from datetime import datetime
from django import forms
from django.utils import timezone
from core.models import Empresa
from core.tenancy import empresa_do_usuario
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
            'empresa',
            'ticket',
            'status',
            'emergencial',
            'data_finalizar',
            'descricao'
        ]

        help_texts = {
            'ticket': 'Opcional. Deixe em branco para gerar ano e mês + sequência de três dígitos (ex.: 2610001).',
        }

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
                'placeholder': 'Deixe em branco para gerar automaticamente'
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
        self.fields['ticket'].required = False
        if self.user and self.user.is_superuser:
            self.fields['empresa'].queryset = Empresa.objects.filter(ativo=True)
            self.fields['empresa'].required = True
            self.fields['empresa'].widget.attrs['class'] = 'form-select'
            if self.instance.pk:
                self.fields['empresa'].disabled = True
                self.fields['empresa'].required = False
        else:
            self.fields.pop('empresa', None)
            if self.user and not self.instance.pk:
                self.instance.empresa = empresa_do_usuario(self.user)
        if self.instance.pk:
            self.fields['ticket'].help_text = 'Deixe em branco para manter o número atual.'

        # Esconde o campo emergencial para usuários não superuser
        if not self.instance.pk and self.user and not self.user.is_superuser:
            self.fields['emergencial'].widget = forms.HiddenInput()
            self.fields['emergencial'].required = False

    def clean_ticket(self):
        codigo = self.cleaned_data.get('ticket', '')
        if self.instance.pk and not codigo:
            return self.instance.ticket
        return codigo


class AssinanteTicketForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['ticket'].help_text = 'Deixe em branco para manter o número atual.'

    def clean_ticket(self):
        codigo = self.cleaned_data.get('ticket', '')
        if self.instance.pk and not codigo:
            return self.instance.ticket
        return codigo

    class Meta:
        model = Ticket
        fields = ['ticket', 'descricao']
        labels = {'ticket': 'Número do Ticket', 'descricao': 'Descrição do serviço'}
        help_texts = {'ticket': TicketForm.Meta.help_texts['ticket']}
        widgets = {
            'ticket': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Deixe em branco para gerar automaticamente',
            }),
            'descricao': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Descreva o problema ou o serviço que você precisa.',
            }),
        }


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
                'placeholder': 'Ex: 5.50',
                'step': '0.01',
                'min': '0'
            }),
        }

class FinanceiroFormMixin:
    """Valida novas movimentações sem atribuir datas ao histórico desconhecido."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._novo_lancamento = not bool(self.instance.pk)
        self._situacao_original = getattr(self.instance, self.campo_situacao)
        self._data_real_original = getattr(self.instance, self.campo_data_real)
        campos_financeiros = (self.campo_valor, 'data_vencimento', self.campo_data_real)
        if self.is_bound and not self._novo_lancamento:
            # Uma edição de descrição/comprovante não apaga dados que não enviou.
            self.data = self.data.copy()
            for nome in campos_financeiros:
                if nome not in self.data:
                    self.data[nome] = getattr(self.instance, nome)
        self.fields[self.campo_valor].required = (
            self._novo_lancamento or getattr(self.instance, self.campo_valor) is not None
        )
        self.fields['data_vencimento'].required = (
            self._novo_lancamento or self.instance.data_vencimento is not None
        )
        self.fields[self.campo_data_real].required = False

    def clean(self):
        cleaned = super().clean()
        valor = cleaned.get(self.campo_valor)
        if valor is not None and valor <= 0:
            self.add_error(self.campo_valor, 'Informe um valor maior que zero.')

        if self.campo_situacao not in cleaned:
            return cleaned
        liquidado = cleaned[self.campo_situacao]
        data_real = cleaned.get(self.campo_data_real)
        if (
            not self._novo_lancamento and liquidado and self._situacao_original
            and data_real is None and self.campo_data_real not in self.errors
        ):
            # Deixar em branco não remove uma baixa histórica sem reabertura.
            data_real = cleaned[self.campo_data_real] = self._data_real_original
        if not liquidado and self._situacao_original and not self._novo_lancamento:
            # Reabrir a movimentação desfaz a baixa; editar o legado não a desfaz.
            cleaned[self.campo_data_real] = None
            return cleaned
        if liquidado and (self._novo_lancamento or not self._situacao_original) and data_real is None:
            self.add_error(self.campo_data_real, 'Informe a data em que a movimentação foi liquidada.')
        if data_real is not None and data_real != self._data_real_original:
            if not liquidado:
                self.add_error(self.campo_data_real, 'Marque a movimentação como liquidada para informar esta data.')
            futura = (
                data_real > timezone.now() if isinstance(data_real, datetime)
                else data_real > timezone.localdate()
            )
            if futura:
                self.add_error(self.campo_data_real, 'A data de liquidação não pode estar no futuro.')
        return cleaned


class PagamentoForm(FinanceiroFormMixin, forms.ModelForm):
    campo_valor = 'valor_pagamento'
    campo_situacao = 'status_pagamento'
    campo_data_real = 'data_pagamento_realizado'

    class Meta:
        model = Pagamentos
        fields = [
            'tipo', 'valor_pagamento', 'status_pagamento',
            'data_vencimento', 'data_pagamento_realizado',
        ]
        labels = {
            'data_vencimento': 'Data de vencimento',
            'data_pagamento_realizado': 'Data do pagamento realizado',
            'status_pagamento': 'Pago',
        }
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'valor_pagamento': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'Ex: 100.00', 'step': '0.01', 'min': '0.01',
            }),
            'status_pagamento': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'data_vencimento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'data_pagamento_realizado': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
        }


class AnexoForm(forms.ModelForm):
    class Meta:
        model = Anexo
        fields = ['arquivo', 'descricao_anexo']  # 'nome_arquivo' removido, pois será derivado do arquivo
        widgets = {
            'descricao_anexo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Descrição (opcional)'}),
            'arquivo': forms.FileInput(attrs={'class': 'form-control'}),
        }


class RecebimentosForm(FinanceiroFormMixin, forms.ModelForm):
    campo_valor = 'valor_recebimento'
    campo_situacao = 'status_recebimento'
    campo_data_real = 'data_recebimento_realizado'

    class Meta:
        model = Recebimentos
        fields = [
            'numero_nota_fiscal', 'serie_nota_fiscal', 'data_emissao',
            'data_vencimento', 'valor_recebimento', 'status_recebimento',
            'descricao_recebimento', 'forma_pagamento', 'tipo_pagamento',
            'data_recebimento_realizado',
        ]
        widgets = {
            'data_emissao': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'data_vencimento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'valor_recebimento': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'descricao_recebimento': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'data_recebimento_realizado': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M:%S',
                attrs={'type': 'datetime-local', 'step': '1', 'class': 'form-control'},
            ),
        }
        labels = {
            'numero_nota_fiscal': 'Número da Nota Fiscal',
            'serie_nota_fiscal': 'Série da Nota Fiscal',
            'data_emissao': 'Data de Emissão',
            'data_vencimento': 'Data de Vencimento',
            'valor_recebimento': 'Valor',
            'status_recebimento': 'Status',
            'descricao_recebimento': 'Descrição',
            'forma_pagamento': 'Forma de Pagamento',
            'tipo_pagamento': 'Tipo de Pagamento',
            'data_recebimento_realizado': 'Data e hora do recebimento',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status_recebimento'].required = True
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs.setdefault('class', 'form-control')

    def clean_data_recebimento_realizado(self):
        value = self.cleaned_data.get('data_recebimento_realizado')
        original = self._data_real_original
        # O navegador exibe segundos; conserva a precisão do registro sem alteração.
        if original is not None and value is not None and original.replace(microsecond=0) == value:
            return original
        return value

    def save(self, commit=True):
        # A confirmação acompanha a fonte principal, sem aceitar checkbox forjado.
        self.instance.recebimento_realizado = bool(self.cleaned_data.get('status_recebimento'))
        return super().save(commit=commit)


class EditarRecebimentoForm(RecebimentosForm):
    pass
