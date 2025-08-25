# forms.py
from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from .models import Empresa, HorarioFuncionamento, Funcionario, Servico

class EmpresaForm(forms.ModelForm):
    # Sobrescrevendo campos para melhor validação
    cnpj = forms.CharField(
        label=_('CNPJ'),
        max_length=18,
        widget=forms.TextInput(attrs={
            'placeholder': '00.000.000/0000-00',
            'class': 'cnpj-mask'
        }),
        validators=[RegexValidator(
            regex=r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$',
            message='CNPJ deve estar no formato: 00.000.000/0000-00'
        )]
    )
    
    telefone = forms.CharField(
        label=_('Telefone'),
        max_length=15,
        widget=forms.TextInput(attrs={
            'placeholder': '(00) 00000-0000',
            'class': 'phone-mask'
        }),
        validators=[RegexValidator(
            regex=r'^\(\d{2}\) \d{4,5}-\d{4}$',
            message='Telefone deve estar no formato: (00) 00000-0000'
        )]
    )
    
    cep = forms.CharField(
        label=_('CEP'),
        max_length=9,
        widget=forms.TextInput(attrs={
            'placeholder': '00000-000',
            'class': 'cep-mask',
            'onblur': 'buscarCEP()'
        })
    )

    data_fundacao = forms.DateField(
        label=_('Data de Fundação'),
        required=False,
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                'class': 'form-control'
            }
        ),
        input_formats=['%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y']
    )

    class Meta:
        model = Empresa
        fields = [
            'nome_fantasia', 'razao_social', 'cnpj', 'tipo_empresa',
            'email', 'telefone', 'whatsapp',
            'cep', 'endereco', 'numero', 'complemento', 'bairro', 'cidade', 'estado',
            'data_fundacao', 'descricao', 'missao', 'visao', 'valores',
            'website', 'facebook', 'instagram', 'linkedin', 'twitter'
        ]
        widgets = {
            'nome_fantasia': forms.TextInput(attrs={
                'placeholder': 'Nome fantasia da sua empresa',
                'class': 'form-control'
            }),
            'razao_social': forms.TextInput(attrs={
                'placeholder': 'Razão social completa',
                'class': 'form-control'
            }),
            'email': forms.EmailInput(attrs={
                'placeholder': 'email@empresa.com',
                'class': 'form-control'
            }),
            'whatsapp': forms.TextInput(attrs={
                'placeholder': '(00) 00000-0000',
                'class': 'form-control phone-mask'
            }),
            'endereco': forms.TextInput(attrs={
                'placeholder': 'Rua, Avenida, etc...',
                'class': 'form-control'
            }),
            'numero': forms.TextInput(attrs={
                'placeholder': '123',
                'class': 'form-control'
            }),
            'complemento': forms.TextInput(attrs={
                'placeholder': 'Sala, Andar, Bloco...',
                'class': 'form-control'
            }),
            'bairro': forms.TextInput(attrs={
                'placeholder': 'Nome do bairro',
                'class': 'form-control'
            }),
            'cidade': forms.TextInput(attrs={
                'placeholder': 'Nome da cidade',
                'class': 'form-control'
            }),
            'estado': forms.Select(attrs={
                'class': 'form-control'
            }),
            'data_fundacao': forms.DateInput(
                format='%Y-%m-%d',
                attrs={
                    'type': 'date',
                    'class': 'form-control'
                }
            ),
            'descricao': forms.Textarea(attrs={
                'placeholder': 'Descreva sua empresa...',
                'class': 'form-control',
                'rows': 3
            }),
            'missao': forms.Textarea(attrs={
                'placeholder': 'Qual é a missão da sua empresa?',
                'class': 'form-control',
                'rows': 2
            }),
            'visao': forms.Textarea(attrs={
                'placeholder': 'Qual é a visão da sua empresa?',
                'class': 'form-control',
                'rows': 2
            }),
            'valores': forms.Textarea(attrs={
                'placeholder': 'Quais são os valores da sua empresa?',
                'class': 'form-control',
                'rows': 2
            }),
            'website': forms.URLInput(attrs={
                'placeholder': 'https://www.suaempresa.com',
                'class': 'form-control'
            }),
            'facebook': forms.URLInput(attrs={
                'placeholder': 'https://facebook.com/suaempresa',
                'class': 'form-control'
            }),
            'instagram': forms.URLInput(attrs={
                'placeholder': 'https://instagram.com/suaempresa',
                'class': 'form-control'
            }),
            'linkedin': forms.URLInput(attrs={
                'placeholder': 'https://linkedin.com/company/suaempresa',
                'class': 'form-control'
            }),
            'twitter': forms.URLInput(attrs={
                'placeholder': 'https://twitter.com/suaempresa',
                'class': 'form-control'
            }),
            'tipo_empresa': forms.Select(attrs={
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Adicionando classes CSS a todos os campos
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'form-control'
        
        # Garantir que a data esteja no formato correto para o input date
        if self.instance and self.instance.data_fundacao:
            self.initial['data_fundacao'] = self.instance.data_fundacao.strftime('%Y-%m-%d')
            
class HorarioFuncionamentoForm(forms.ModelForm):
    class Meta:
        model = HorarioFuncionamento
        fields = ['dia_semana', 'abre_as', 'fecha_as', 'fechado']
        widgets = {
            'abre_as': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'fecha_as': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'fechado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class FuncionarioForm(forms.ModelForm):
    class Meta:
        model = Funcionario
        fields = ['nome', 'cargo', 'email', 'telefone', 'foto', 'descricao', 'ordem_exibicao']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefone': forms.TextInput(attrs={
                'class': 'form-control phone-mask',
                'placeholder': '(00) 00000-0000'
            }),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'ordem_exibicao': forms.NumberInput(attrs={'class': 'form-control'}),
            'foto': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'cargo': forms.Select(attrs={'class': 'form-control'}),
        }

class ServicoForm(forms.ModelForm):
    class Meta:
        model = Servico
        fields = ['nome', 'descricao', 'icone', 'imagem', 'ordem_exibicao']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'icone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'fas fa-cog ou bi bi-gear'
            }),
            'ordem_exibicao': forms.NumberInput(attrs={'class': 'form-control'}),
            'imagem': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
