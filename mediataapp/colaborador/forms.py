from django import forms
from .models import Colaborador
from clientes.forms import EmpresaCadastroForm
from core.tenancy import usuarios_da_empresa

class ColaboradorForm(EmpresaCadastroForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.actor is not None and 'user' in self.fields:
            self.fields['user'].queryset = usuarios_da_empresa(self.actor).exclude(
                is_superuser=True,
            ).exclude(groups__name='assinante').distinct()
            if self.instance.pk:
                self.fields['user'].queryset = self.fields['user'].queryset.filter(
                    vinculo_empresa__empresa_id=self.instance.empresa_id,
                )
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
        exclude = ['empresa']
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
        user = cleaned_data.get('user')
        if self.actor is not None and user is not None:
            from core.tenancy import empresa_do_usuario

            empresa = empresa_do_usuario(user)
            if empresa is None or empresa.pk != self.instance.empresa_id:
                self.add_error('user', 'O usuário vinculado precisa pertencer à mesma empresa do colaborador.')
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
