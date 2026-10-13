from django.contrib import admin
from .models import Cliente
from .forms import ClienteForm
from core.admin_access import SuperuserOnlyAdminMixin

@admin.register(Cliente)
class ClienteAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    form = ClienteForm
    list_display = ['nome_razao_social', 'cpf_cnpj', 'email', 'ativo']
    search_fields = ['nome_razao_social', 'cpf_cnpj', 'email']
    list_filter = ['tipo_pessoa', 'ativo']
