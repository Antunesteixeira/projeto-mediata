# admin.py
from django.contrib import admin
from .models import Empresa, HorarioFuncionamento, Funcionario, Servico

class HorarioFuncionamentoInline(admin.TabularInline):
    model = HorarioFuncionamento
    extra = 7
    max_num = 7

class FuncionarioInline(admin.TabularInline):
    model = Funcionario
    extra = 1

class ServicoInline(admin.TabularInline):
    model = Servico
    extra = 1

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ['nome_fantasia', 'cnpj', 'cidade', 'estado', 'ativo']
    list_filter = ['ativo', 'estado', 'tipo_empresa']
    search_fields = ['nome_fantasia', 'razao_social', 'cnpj']
    inlines = [HorarioFuncionamentoInline, FuncionarioInline, ServicoInline]
    fieldsets = [
        ('Informações Básicas', {
            'fields': ['nome_fantasia', 'razao_social', 'cnpj', 'tipo_empresa']
        }),
        ('Contato', {
            'fields': ['email', 'telefone', 'whatsapp']
        }),
        ('Endereço', {
            'fields': ['cep', 'endereco', 'numero', 'complemento', 'bairro', 'cidade', 'estado']
        }),
        ('Sobre a Empresa', {
            'fields': ['data_fundacao', 'descricao', 'missao', 'visao', 'valores']
        }),
        ('Redes Sociais', {
            'fields': ['website', 'facebook', 'instagram', 'linkedin', 'twitter'],
            'classes': ['collapse']
        }),
        ('Configurações', {
            'fields': ['ativo'],
            'classes': ['collapse']
        })
    ]

@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    list_display = ['nome', 'cargo', 'empresa', 'ativo']
    list_filter = ['cargo', 'ativo', 'empresa']
    search_fields = ['nome', 'email']

@admin.register(Servico)
class ServicoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'empresa', 'ativo']
    list_filter = ['ativo', 'empresa']
    search_fields = ['nome']
