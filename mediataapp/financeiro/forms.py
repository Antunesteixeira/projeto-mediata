from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from core.models import Empresa
from core.tenancy import empresa_do_usuario, pode_operar_tickets
from .models import LancamentoManual


class FiltroFinanceiroForm(forms.Form):
    operacao = forms.ChoiceField(
        label='Operação',
        choices=(('todas', 'Créditos e débitos'), ('credito', 'Créditos'), ('debito', 'Débitos')),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    situacao = forms.ChoiceField(
        label='Situação',
        choices=(
            ('todas', 'Todas'), ('pago', 'Pago'), ('recebido', 'Recebido'),
            ('vencido', 'Vencido'), ('aberto', 'Em aberto (a vencer)'),
        ),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    periodo = forms.ChoiceField(
        label='Período do vencimento',
        choices=(
            ('todos', 'Todos os períodos'), ('30', 'Próximos 30 dias'),
            ('60', 'Próximos 60 dias'), ('90', 'Próximos 90 dias'),
            ('personalizado', 'Personalizado'),
        ),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    data_inicio = forms.DateField(
        label='Data inicial', required=False, input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
    )
    data_fim = forms.DateField(
        label='Data final', required=False, input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
    )

    def __init__(self, data=None, *, hoje=None, **kwargs):
        self.hoje = hoje or timezone.localdate()
        source = data.copy() if data is not None else {}
        for name, default in (('operacao', 'todas'), ('situacao', 'todas'), ('periodo', 'todos')):
            source.setdefault(name, default)
        super().__init__(source, **kwargs)

    def clean(self):
        cleaned = super().clean()
        periodo = cleaned.get('periodo')
        if periodo == 'personalizado':
            inicio, fim = cleaned.get('data_inicio'), cleaned.get('data_fim')
            if inicio is None and 'data_inicio' not in self.errors:
                self.add_error('data_inicio', 'Informe a data inicial.')
            if fim is None and 'data_fim' not in self.errors:
                self.add_error('data_fim', 'Informe a data final.')
            if inicio and fim and inicio > fim:
                self.add_error('data_fim', 'A data final deve ser igual ou posterior à data inicial.')
        elif periodo in ('30', '60', '90'):
            cleaned['data_inicio'] = self.hoje
            cleaned['data_fim'] = self.hoje + timedelta(days=int(periodo) - 1)
        elif periodo == 'todos':
            cleaned['data_inicio'] = cleaned['data_fim'] = None
        return cleaned

    def apresentar_intervalo(self):
        """Os campos exibem o mesmo intervalo que foi aplicado no servidor."""
        self.data = self.data.copy()
        for field in ('data_inicio', 'data_fim'):
            value = self.cleaned_data.get(field)
            self.data[field] = value.isoformat() if value else ''


class LancamentoManualForm(forms.ModelForm):
    class Meta:
        model = LancamentoManual
        fields = [
            'empresa', 'operacao', 'descricao', 'contraparte', 'valor',
            'data_vencimento', 'liquidado', 'data_quitacao',
        ]
        labels = {
            'contraparte': 'Cliente / favorecido', 'liquidado': 'Lançamento quitado',
            'data_vencimento': 'Data de vencimento', 'data_quitacao': 'Data da quitação',
        }
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
            'operacao': forms.Select(attrs={'class': 'form-select'}),
            'descricao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Descreva a entrada ou despesa'}),
            'contraparte': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome de quem paga ou recebe (opcional)'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'data_vencimento': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'liquidado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'data_quitacao': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
        }
        help_texts = {
            'liquidado': 'Marque somente se o valor já foi pago ou recebido.',
            'data_quitacao': 'Obrigatória quando o lançamento estiver quitado.',
        }

    def __init__(self, *args, actor=None, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        for name in ('data_vencimento', 'data_quitacao'):
            self.fields[name].input_formats = ['%Y-%m-%d']
        if not self.instance.pk and not self.initial.get('operacao'):
            self.initial['operacao'] = LancamentoManual.Operacao.DEBITO
        if actor is not None and actor.is_superuser:
            permitidas = Q(ativo=True)
            if self.instance.pk:
                permitidas |= Q(pk=self.instance.empresa_id)
                self.fields['empresa'].disabled = True
            self.fields['empresa'].queryset = Empresa.objects.filter(permitidas).order_by('nome_fantasia')
        else:
            self.fields.pop('empresa', None)
            if actor is not None and not self.instance.pk:
                self.instance.empresa = empresa_do_usuario(actor)

    def clean(self):
        cleaned = super().clean()
        if self.actor is None or not pode_operar_tickets(self.actor):
            raise ValidationError('Seu acesso não permite cadastrar lançamentos financeiros.')
        if not self.actor.is_superuser:
            empresa = empresa_do_usuario(self.actor)
            if empresa is None or (self.instance.pk and self.instance.empresa_id != empresa.pk):
                raise ValidationError('Você pode gerenciar somente lançamentos da sua empresa.')
        if not cleaned.get('liquidado'):
            # O status informado define a baixa; reabrir também remove a data anterior.
            cleaned['data_quitacao'] = None
        return cleaned
