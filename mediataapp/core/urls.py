from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name="index"),
    path('logout/', views.sair, name="logout"),
    path('dashboard/', views.dashboard, name="dashboard"),
    path('api/buscar-itens/', views.buscar_itens, name='buscar-itens'),
    path('empresa/cadastrar/', views.EmpresaCreateView.as_view(), name='empresa_cadastrar'),
    path('empresa/editar/<int:pk>/', views.EmpresaUpdateView.as_view(), name='empresa_editar'),
    path('empresa/<int:pk>/', views.EmpresaDetailView.as_view(), name='empresa_perfil'),
    path('empresas/', views.EmpresaListView.as_view(), name='empresa_lista'),
    path('empresa/success/', views.success_view, name='empresa_success'),
]