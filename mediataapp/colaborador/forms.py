from django import forms
from .models import Colaborador

class ColaboradorForm(forms.ModelForm):
    data_nascimento = forms.DateField(
        required=False,  # Torna o campo não obrigatório
        widget=forms.DateInput(
            attrs={
                'class': 'form-control',
                'type': 'date',
            },
            format='%Y-%m-%d'  # formato compatível com input type="date"
        )
    )
    
    class Meta:
        model = Colaborador
        fields = '__all__'
        widgets = {
            'tipo_pessoa': forms.Select(attrs={'class': 'form-select'}),
            'nome_completo': forms.TextInput(attrs={'class': 'form-control'}),
            'funcao': forms.TextInput(attrs={'class': 'form-control'}),
            'cpf': forms.TextInput(attrs={'class': 'form-control'}),
            'data_nascimento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'razao_social': forms.TextInput(attrs={'class': 'form-control'}),
            'cnpj': forms.TextInput(attrs={'class': 'form-control'}),
            'nome_fantasia': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'endereco': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'banco': forms.TextInput(attrs={'class': 'form-control'}),
            'agencia': forms.TextInput(attrs={'class': 'form-control'}),
            'conta': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_conta': forms.Select(attrs={'class': 'form-select'}),
            'tipo_chave_pix': forms.Select(attrs={'class': 'form-select'}),
            'chave_pix': forms.TextInput(attrs={'class': 'form-control'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        tipo_pessoa = cleaned_data.get('tipo_pessoa')

        if tipo_pessoa == 'PF':
            if not cleaned_data.get('nome_completo'):
                self.add_error('nome_completo', 'Informe o nome completo para Pessoa Física.')
            if not cleaned_data.get('cpf'):
                self.add_error('cpf', 'Informe o CPF.')
            # Zera campos de PJ para evitar lixo no banco
            cleaned_data['razao_social'] = None
            cleaned_data['cnpj'] = None

        elif tipo_pessoa == 'PJ':
            if not cleaned_data.get('razao_social'):
                self.add_error('razao_social', 'Informe a Razão Social para Pessoa Jurídica.')
            if not cleaned_data.get('cnpj'):
                self.add_error('cnpj', 'Informe o CNPJ.')
            # Zera campos de PF
            cleaned_data['nome_completo'] = None
            cleaned_data['cpf'] = None

        return cleaned_data