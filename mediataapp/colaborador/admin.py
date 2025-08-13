from django.contrib import admin
from .models import Colaborador
from .forms import ColaboradorForm

@admin.register(Colaborador)
class ColaboradorAdmin(admin.ModelAdmin):
    form = ColaboradorForm
    list_display = ['id', 'tipo_pessoa', 'nome_ou_razao', 'email', 'telefone', 'banco', 'tipo_chave_pix']
    list_filter = ['tipo_pessoa', 'banco', 'tipo_chave_pix']
    search_fields = ['nome_completo', 'razao_social', 'cpf', 'cnpj', 'email']

    fieldsets = (
        ('Tipo de Pessoa', {
            'fields': ('tipo_pessoa',)
        }),
        ('Pessoa Física', {
            'fields': ('nome_completo', 'cpf', 'data_nascimento'),
        }),
        ('Pessoa Jurídica', {
            'fields': ('razao_social', 'nome_fantasia', 'cnpj'),
        }),
        ('Contato', {
            'fields': ('email', 'telefone', 'endereco'),
        }),
        ('Dados Bancários', {
            'fields': ('banco', 'agencia', 'conta', 'tipo_conta', 'tipo_chave_pix', 'chave_pix'),
        }),
    )

    def nome_ou_razao(self, obj):
        return obj.nome_completo or obj.razao_social
    nome_ou_razao.short_description = 'Nome / Razão Social'
