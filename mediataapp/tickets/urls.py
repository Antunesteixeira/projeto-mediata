from django.urls import path

from . import views

urlpatterns = [
    path('', views.tickets, name="index-tickets"),
    path('cadastro-ticket/', views.cadastro_ticket, name="cadastro-ticket"),
    path('ticket/<uuid:key>', views.exibirticket, name="exibir-ticket"),
    path('editar-ticket/<uuid:key>', views.editar_ticket, name="editar-ticket"),
    path('teste/', views.selecionar_ticket),
    #path('buscar-tickets/', views.buscar_tickets, name='buscar_tickets'),
    path('buscar/', views.buscar_tickets, name='buscar_tickets'),
    path('deletar-ticket/<uuid:key>', views.deletar_ticket, name='deletar-ticket'),
]