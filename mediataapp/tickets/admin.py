from django.contrib import admin

from .models import Ticket, Orcamento, Servico, Material

admin.site.register(Ticket)
admin.site.register(Orcamento)
admin.site.register(Servico)
admin.site.register(Material)