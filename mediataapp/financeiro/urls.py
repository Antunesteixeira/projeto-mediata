from django.urls import path
from . import views

app_name = 'financeiro'
urlpatterns = [
    path('', views.index, name='index'),
    path('novo/', views.novo_lancamento, name='novo-lancamento'),
    path('manuais/<int:pk>/editar/', views.editar_manual, name='editar-manual'),
    path('pagamentos/<int:pk>/editar/', views.editar_pagamento, name='editar-pagamento'),
    path('recebimentos/<int:pk>/editar/', views.editar_recebimento, name='editar-recebimento'),
]
