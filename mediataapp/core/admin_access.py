from django.contrib import admin


class SuperuserOnlyAdminMixin:
    """Reserve o admin global para a administração da plataforma."""

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if self.has_module_permission(request) else queryset.none()

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)
        if not getattr(form_class, 'supports_actor', False):
            return form_class

        class RequestForm(form_class):
            def __init__(self, *args, **form_kwargs):
                form_kwargs['actor'] = request.user
                super().__init__(*args, **form_kwargs)

        return RequestForm


class SuperuserOnlyModelAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    pass
