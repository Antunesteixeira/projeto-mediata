from django.urls import path

from . import views

urlpatterns = [
    path('', views.tickets, name="index-tickets"),
    path('cadastro-ticket/', views.cadastro_ticket, name="cadastro-ticket"),
    path('ticket/<uuid:key>', views.exibirticket, name="exibir-ticket"),
    path('editar-ticket/<uuid:key>', views.editar_ticket, name="editar-ticket"),
]