from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User

from core.admin_access import SuperuserOnlyAdminMixin
from .models import UsuarioEmpresa


class UsuarioEmpresaInline(admin.StackedInline):
    model = UsuarioEmpresa
    max_num = 1
    extra = 0


class PlatformUserAdmin(SuperuserOnlyAdminMixin, UserAdmin):
    inlines = [UsuarioEmpresaInline]


class PlatformGroupAdmin(SuperuserOnlyAdminMixin, GroupAdmin):
    pass


admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, PlatformUserAdmin)
admin.site.register(Group, PlatformGroupAdmin)


@admin.register(UsuarioEmpresa)
class UsuarioEmpresaAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('usuario', 'empresa')
    list_select_related = ('usuario', 'empresa')
