from django.urls import path

from . import views


app_name = 'whatsapp'
urlpatterns = [
    path('', views.index, name='index'),
    path('configurar/<int:empresa_id>/', views.configurar, name='configurar'),
    path('conectar/<int:empresa_id>/', views.conectar, name='conectar'),
    path('status/<int:empresa_id>/', views.status, name='status'),
    path('desconectar/<int:empresa_id>/', views.desconectar, name='desconectar'),
    path('webhook/<uuid:identificador>/', views.webhook, name='webhook'),
]
