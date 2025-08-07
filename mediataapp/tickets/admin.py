from django.contrib import admin

from .models import Ticket, Orcamento, Servico, Material, ItemOrcamento, HistoricoTicket, Pagamentos

admin.site.register(Ticket)
admin.site.register(Orcamento)
admin.site.register(Servico)
admin.site.register(Material)
admin.site.register(ItemOrcamento)
admin.site.register(HistoricoTicket)
admin.site.register(Pagamentos)