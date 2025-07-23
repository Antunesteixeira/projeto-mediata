from django.urls import path

from . import views

urlpatterns = [
    path('', views.tickets, name="index-tickets"),
    path('cadastro-ticket/', views.cadastro_ticket, name="cadastro-ticket"),
]