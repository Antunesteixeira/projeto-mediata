from django import forms
from .models import Cliente
from core.models import Empresa
from core.tenancy import empresa_do_usuario
from django.db import IntegrityError, transaction


def salvar_form_empresa(form):
    try:
        with transaction.atomic():
            return form.save()
    except IntegrityError:
        form.add_error(None, 'Já existe um cadastro com estes dados na empresa. Verifique os campos informados.')
        return None


class EmpresaCadastroForm(forms.ModelForm):
    supports_actor = True
    empresa = forms.ModelChoiceField(
        queryset=Empresa.objects.none(), required=False, label='Empresa',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, actor=None, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        if actor is not None and actor.is_superuser:
            self.fields['empresa'].required = True
            if self.instance.pk:
                self.fields['empresa'].queryset = Empresa.objects.filter(pk=self.instance.empresa_id)
                self.fields['empresa'].initial = self.instance.empresa_id
                self.initial['empresa'] = self.instance.empresa_id
                self.fields['empresa'].disabled = True
            else:
                self.fields['empresa'].queryset = Empresa.objects.filter(ativo=True)
        else:
            self.fields.pop('empresa', None)

    def clean(self):
        cleaned_data = super().clean()
        if self.actor is None:
            return cleaned_data
        if self.actor.is_superuser:
            empresa = cleaned_data.get('empresa')
        else:
            empresa = empresa_do_usuario(self.actor)
            if empresa is None:
                raise forms.ValidationError('Seu usuário precisa estar vinculado a uma empresa ativa.')
            if self.instance.pk and self.instance.empresa_id != empresa.pk:
                raise forms.ValidationError('Este cadastro pertence a outra empresa.')
        if empresa is not None:
            self.instance.empresa = empresa
        return cleaned_data

    def _get_validation_exclusions(self):
        exclusions = super()._get_validation_exclusions()
        if self.instance.empresa_id is not None:
            # A empresa é atribuída pelo servidor, mas participa da unicidade.
            exclusions.discard('empresa')
        return exclusions

class ClienteForm(EmpresaCadastroForm):
    class Meta:
        model = Cliente
        exclude = ['empresa']
        widgets = {
            'tipo_pessoa': forms.RadioSelect(choices=Cliente.TIPO_PESSOA_CHOICES),
            'nome_razao_social': forms.TextInput(attrs={'class': 'form-control'}),
            'sobrenome_nome_fantasia': forms.TextInput(attrs={'class': 'form-control'}),
            'cpf_cnpj': forms.TextInput(attrs={'class': 'form-control'}),
            'rg_ie': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'celular': forms.TextInput(attrs={'class': 'form-control'}),
            'cep': forms.TextInput(attrs={'class': 'form-control'}),
            'endereco': forms.TextInput(attrs={'class': 'form-control'}),
            'numero': forms.TextInput(attrs={'class': 'form-control'}),
            'complemento': forms.TextInput(attrs={'class': 'form-control'}),
            'bairro': forms.TextInput(attrs={'class': 'form-control'}),
            'cidade': forms.TextInput(attrs={'class': 'form-control'}),
            'estado': forms.TextInput(attrs={'class': 'form-control'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
