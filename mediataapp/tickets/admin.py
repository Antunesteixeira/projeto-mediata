from django.contrib import admin
from core.admin_access import SuperuserOnlyAdminMixin

from .models import Ticket, Orcamento, Servico, Material, ItemOrcamento, HistoricoTicket, Pagamentos, Anexo, Recebimentos   

class EmpresaAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    pass


admin.site.register(Ticket, EmpresaAdmin)
admin.site.register(Orcamento, EmpresaAdmin)
admin.site.register(Servico, EmpresaAdmin)
admin.site.register(Material, EmpresaAdmin)
admin.site.register(ItemOrcamento, EmpresaAdmin)
admin.site.register(HistoricoTicket, EmpresaAdmin)
admin.site.register(Anexo, EmpresaAdmin)
admin.site.register(Recebimentos, EmpresaAdmin)



@admin.register(Pagamentos)
class PagamentosAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('ticket_pagamento', 'tipo', 'valor_pagamento', 'data_pagamento', 'status_pagamento')
    list_filter = ('status_pagamento', 'tipo')
