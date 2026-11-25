from django.contrib import admin

from core.admin_access import SuperuserOnlyAdminMixin

from .models import ConexaoWhatsApp, EnvioTicketWhatsApp


@admin.register(ConexaoWhatsApp)
class ConexaoWhatsAppAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('empresa', 'estado', 'instancia_criada', 'atualizado_em')
    list_filter = ('estado',)
    fields = ('empresa', 'estado', 'instancia_criada', 'ultimo_evento_em', 'criado_em', 'atualizado_em')
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EnvioTicketWhatsApp)
class EnvioTicketWhatsAppAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('ticket_numero', 'empresa', 'colaborador_nome', 'telefone_mascarado', 'estado', 'criado_em')
    list_filter = ('estado',)
    fields = (
        'empresa', 'ticket', 'colaborador', 'usuario', 'ticket_numero',
        'colaborador_nome', 'telefone_mascarado', 'estado', 'codigo_resultado',
        'id_provedor', 'criado_em', 'atualizado_em', 'finalizado_em',
    )
    readonly_fields = fields
    list_select_related = ('empresa',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
