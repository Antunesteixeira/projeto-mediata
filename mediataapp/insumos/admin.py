from django.contrib import admin

# Register your models here.
from .models import Insumos
from .forms import InsumoForm
from core.admin_access import SuperuserOnlyAdminMixin

@admin.register(Insumos)
class InsumosAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    form = InsumoForm
