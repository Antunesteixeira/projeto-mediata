from django.urls import path
from . import views

urlpatterns = [
    path('cadastrar/', views.cadastrar_colaborador, name='cadastrar_colaborador'),
    path('', views.lista_colaboradores, name='lista_colaboradores'),  # opcional
    path('editar-colaborador/<int:colaborador_id>/', views.editar_colaborador, name='editar-colaborador'),
    path('deletar/<int:colaborador_id>/', views.deletar_colaborador, name='deletar-colaborador'),
]
