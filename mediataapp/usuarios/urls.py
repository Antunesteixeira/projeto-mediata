from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    path('cadastro-usuarios/', views.cadastro_usuarios, name="cadastro-usuarios"),
]