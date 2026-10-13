from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group
from django.db import transaction

from core.models import Empresa
from core.tenancy import empresa_do_usuario, pode_gerenciar_empresa
from rolepermissions.roles import assign_role
from .models import UsuarioEmpresa


ROLE_NAMES = ('gerente', 'operador', 'cliente', 'colaborador', 'assinante')


class CompanyAccessFormMixin:
    group_field_name = 'group'

    def _configure_access(self, actor):
        self.actor = actor
        company = empresa_do_usuario(actor) if actor is not None else None
        is_admin = bool(actor is not None and actor.is_superuser)
        can_manage = bool(actor is not None and pode_gerenciar_empresa(actor))
        groups = Group.objects.filter(name__in=ROLE_NAMES).order_by('name')
        companies = Empresa.objects.filter(ativo=True)
        if not is_admin:
            groups = groups.exclude(name='assinante')
            companies = companies.filter(pk=company.pk) if company is not None else companies.none()
        self.fields[self.group_field_name].queryset = groups
        self.fields['empresa'].queryset = companies
        self.fields['empresa'].help_text = 'Obrigatória para usuários da empresa. Assinantes independentes ficam sem empresa.'
        if self.instance.pk:
            self.initial[self.group_field_name] = self.instance.groups.first()
            try:
                self.initial['empresa'] = self.instance.vinculo_empresa.empresa_id
            except UsuarioEmpresa.DoesNotExist:
                pass
        elif company is not None:
            self.initial['empresa'] = company.pk
        if not is_admin:
            self.fields['empresa'].disabled = True
        if self.instance.pk and not can_manage:
            self.fields[self.group_field_name].required = False
            for name in (self.group_field_name, 'empresa', 'is_active'):
                self.fields[name].disabled = True
        if self.instance.pk and self.instance.is_superuser:
            self.fields[self.group_field_name].required = False
        self.can_manage_access = can_manage

    def clean(self):
        cleaned = super().clean()
        actor = self.actor
        if actor is None or not actor.is_authenticated:
            raise forms.ValidationError('É necessário informar o usuário responsável por este cadastro.')
        if not self.instance.pk and not pode_gerenciar_empresa(actor):
            raise forms.ValidationError('Apenas administradores e gerentes podem cadastrar usuários.')
        if self.instance.pk and not actor.is_superuser:
            if self.instance.is_superuser:
                raise forms.ValidationError('Você não pode alterar uma conta administradora.')
            own_company = empresa_do_usuario(actor)
            target_company = empresa_do_usuario(self.instance)
            if self.instance.pk != actor.pk and (
                not pode_gerenciar_empresa(actor) or own_company is None
                or target_company is None or target_company.pk != own_company.pk
            ):
                raise forms.ValidationError('Você pode gerenciar somente usuários da sua empresa.')
        group = cleaned.get(self.group_field_name)
        if group is not None and group.name == 'assinante':
            if not actor.is_superuser:
                self.add_error(self.group_field_name, 'Somente o administrador gerencia assinantes independentes.')
            cleaned['empresa'] = None
        elif not (self.instance.pk and (self.instance.is_superuser or not self.can_manage_access)) and cleaned.get('empresa') is None:
            self.add_error('empresa', 'Selecione a empresa deste usuário.')
        if self.instance.pk and self.can_manage_access:
            from colaborador.models import Colaborador
            linked = Colaborador.objects.filter(user=self.instance).first()
            if linked is not None:
                company = cleaned.get('empresa')
                independent = group is not None and group.name == 'assinante'
                if independent or company is None or company.pk != linked.empresa_id:
                    self.add_error(
                        self.group_field_name if independent else 'empresa',
                        'Desvincule o usuário do cadastro de colaborador antes de alterar a empresa ou torná-lo assinante independente.',
                    )
        return cleaned

    def _save_access(self, user):
        if not self.can_manage_access:
            return
        group = self.cleaned_data.get(self.group_field_name)
        user.groups.clear()
        # As permissões diretas dos papéis são recalculadas quando o grupo muda.
        user.user_permissions.remove(*user.user_permissions.filter(codename__in={
            'criar_ticket', 'ver_ticket', 'criar_insumo', 'criar_usuarios', 'ver_usuarios',
        }))
        if group is not None:
            assign_role(user, group.name)
        company = self.cleaned_data.get('empresa')
        if group is not None and group.name == 'assinante':
            UsuarioEmpresa.objects.filter(usuario=user).delete()
        elif company is not None:
            UsuarioEmpresa.objects.update_or_create(usuario=user, defaults={'empresa': company})
        elif user.is_superuser:
            UsuarioEmpresa.objects.filter(usuario=user).delete()


class CustomUserCreationForm(CompanyAccessFormMixin, UserCreationForm):
    group = forms.ModelChoiceField(
        queryset=Group.objects.none(), required=True, label='Grupo',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    empresa = forms.ModelChoiceField(
        queryset=Empresa.objects.none(), required=False, label='Empresa',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Digite seu e-mail'}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'group', 'empresa']
        widgets = {'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Digite seu nome de usuário'})}

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_access(actor)
        for name in ('password1', 'password2'):
            self.fields[name].widget.attrs.update({'class': 'form-control', 'placeholder': 'Digite sua senha'})

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            with transaction.atomic():
                user.save()
                self._save_access(user)
        else:
            self.save_m2m = lambda: self._save_access(user)
        return user


class CustomUserEditForm(CompanyAccessFormMixin, forms.ModelForm):
    group_field_name = 'groups'
    groups = forms.ModelChoiceField(
        queryset=Group.objects.none(), required=True, label='Grupo',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    empresa = forms.ModelChoiceField(
        queryset=Empresa.objects.none(), required=False, label='Empresa',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_active = forms.BooleanField(
        required=False, label='Usuário ativo', widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'groups', 'empresa', 'is_active']
        widgets = {
            name: forms.TextInput(attrs={'class': 'form-control'})
            for name in ('username', 'first_name', 'last_name', 'email')
        }

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_access(actor)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            with transaction.atomic():
                user.save()
                self._save_access(user)
        else:
            self.save_m2m = lambda: self._save_access(user)
        return user
