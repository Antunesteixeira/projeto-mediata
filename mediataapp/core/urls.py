from django.urls import path
from django.contrib.auth.views import LogoutView

from . import views
from .health import health_check

urlpatterns = [
    path('', views.index, name="index"),
    path('logout/', LogoutView.as_view(), name="logout"),
    path('dashboard/', views.dashboard, name="dashboard"),
    path('api/buscar-itens/', views.buscar_itens, name='buscar-itens'),
    path('empresa/cadastrar/', views.EmpresaCreateView.as_view(), name='empresa_cadastrar'),
    path('empresa/editar/<int:pk>/', views.EmpresaUpdateView.as_view(), name='empresa_editar'),
    path('empresa/<int:pk>/', views.EmpresaDetailView.as_view(), name='empresa_perfil'),
    path('empresas/', views.EmpresaListView.as_view(), name='empresa_lista'),
    path('empresa/success/', views.success_view, name='empresa_success'),
    path('health/', health_check, name='health'),
]