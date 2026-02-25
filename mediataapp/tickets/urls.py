from django.urls import path

from . import views

urlpatterns = [
    path('', views.tickets, name="index-tickets"),
    path('cadastro-ticket/', views.cadastro_ticket, name="cadastro-ticket"),
    path('ticket/<uuid:key>', views.exibirticket, name="exibir-ticket"),
    path('editar-ticket/<uuid:key>', views.editar_ticket, name="editar-ticket"),
    #path('buscar-tickets/', views.buscar_tickets, name='buscar_tickets'),
    path('buscar/', views.buscar_tickets, name='buscar_tickets'),
    path('deletar-ticket/<uuid:key>', views.deletar_ticket, name='deletar-ticket'),
    path('deletar-item/<int:id>/<uuid:key>', views.deletar_itemorcamento, name='deletar-item'),
    path('update-historico/<uuid:key>', views.update_historico, name='update-historico'),
    # ...outras urls...
    path('editar-pagamento/<int:pagamento_id>/<uuid:key>/', views.editar_pagamento, name='editar-pagamento'),
    path('add-pagamento/<uuid:key>/', views.add_pagamento, name='add-pagamento'),
    #path('editar-pagamento/<int:id>/<uuid:key>', views.editar_pagamento, name='editar-pagamento'),
    path('deletar-pagamento/<int:id>/<uuid:key>', views.deletar_pagamento, name='deletar-pagamento'),
    path('add-colaborador-ticket/<int:id_ticket>', views.addTicketColaborador, name="add-colaborador-ticket"),
    path('cadastrar-colaborador-ticket/<int:id_ticket>/<int:id_colaborador>', views.cadastrarColaboradorTicket, name="cadastrar-colaborador-ticket"),
    path('add-cliente-ticket/<int:id_ticket>', views.addTicketCliente, name='add-cliente-ticket'),
    path('cadastrar-cliente-ticket/<int:id_cliente>/<int:id_ticket>', views.cadastrarTicketCliente, name='cadastrar-cliente-ticket'),
    path('upload-nfe/<uuid:key>/', views.upload_nfe, name='upload-nfe'),
    path('upload-comprovante/<int:id>/<uuid:key>/', views.upload_comprovante, name='upload-comprovante'),
    path('ticket/<str:key>/delete-nfe/', views.delete_nfe, name='delete-nfe'),
    path('ticket/<int:id>/<str:key>/delete-comprovante/', views.delete_comprovante, name='delete-comprovante'),
    path('orcamento/pdf/<int:ticket_id>/', views.gerar_pdf_orcamento, name='gerar_pdf_orcamento'),
    path('deletar-anexo/<int:anexo_id>/<uuid:key>/', views.deletar_anexo, name='deletar-anexo'),    
]