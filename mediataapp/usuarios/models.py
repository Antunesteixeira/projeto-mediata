from django import forms
from django.db import models
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class UsuarioEmpresa(models.Model):
    usuario = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='vinculo_empresa',
    )
    empresa = models.ForeignKey(
        'core.Empresa', on_delete=models.PROTECT, related_name='usuarios_vinculados',
    )

    def __str__(self):
        return f'{self.usuario} — {self.empresa}'
