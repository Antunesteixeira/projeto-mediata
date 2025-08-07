from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    path('', views.usuarios, name="index-usuarios"),
    path('perfil/<int:id>', views.perfil_usuario, name='perfil-usuario'),
    path('editar/<int:user_id>/', views.editar_usuario, name='editar-usuario'),
    path('cadastro-usuarios/', views.register, name="registrar-usuarios"),
    path('editar-usuarios/<int:id>', views.editar_usuarios, name="editar-usuarios"),
]