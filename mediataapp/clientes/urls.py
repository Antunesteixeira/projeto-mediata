from django.urls import path

from . import views

urlpatterns = [
    path('cadastrar/', views.cadastrar_cliente, name='cadastrar-cliente'),
    path('listar/', views.listar_clientes, name='listar-clientes'), 
    path('editar/<int:cliente_id>/', views.editar_cliente, name='editar-cliente'),
  
]