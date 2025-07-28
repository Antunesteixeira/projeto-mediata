from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    path('', views.usuarios, name="index-usuarios"),
    path('cadastro-usuarios/', views.register, name="registrar-usuarios"),
    path('editar-usuarios/', views.editar_usuarios, name="editar-usuarios"),
]