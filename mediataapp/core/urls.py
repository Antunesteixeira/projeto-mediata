from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name="index"),
    path('logout/', views.sair, name="logout"),
    path('dashboard/', views.dashboard, name="dashboard"),
    path('api/buscar-itens/', views.buscar_itens, name='buscar-itens'),
]