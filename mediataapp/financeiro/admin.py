from django.contrib import admin

from core.admin_access import SuperuserOnlyAdminMixin

from .models import LancamentoManual


@admin.register(LancamentoManual)
class LancamentoManualAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        'id', 'empresa', 'operacao', 'descricao', 'valor',
        'data_vencimento', 'liquidado', 'data_quitacao',
    )
    list_filter = ('operacao', 'liquidado', 'empresa')
    search_fields = ('descricao', 'contraparte')
    readonly_fields = ('criado_por', 'criado_em', 'atualizado_em')
    list_select_related = ('empresa', 'criado_por')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)
