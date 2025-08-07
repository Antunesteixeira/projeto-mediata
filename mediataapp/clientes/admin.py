from django.contrib import admin
from .models import Cliente

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['nome_razao_social', 'cpf_cnpj', 'email', 'ativo']
    search_fields = ['nome_razao_social', 'cpf_cnpj', 'email']
    list_filter = ['tipo_pessoa', 'ativo']
