from django.contrib import admin

from .models import Ticket, Orcamento, Servico, Material, ItemOrcamento, HistoricoTicket, Pagamentos, Anexo, Recebimentos   

admin.site.register(Ticket)
admin.site.register(Orcamento)
admin.site.register(Servico)
admin.site.register(Material)
admin.site.register(ItemOrcamento)
admin.site.register(HistoricoTicket)
admin.site.register(Anexo)
admin.site.register(Recebimentos)



@admin.register(Pagamentos)
class PagamentosAdmin(admin.ModelAdmin):
    list_display = ('ticket_pagamento', 'tipo', 'valor_pagamento', 'data_pagamento', 'status_pagamento')
    list_filter = ('status_pagamento', 'tipo')