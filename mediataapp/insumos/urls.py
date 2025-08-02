from django.urls import path, include

from . import views

urlpatterns = [
    path('', views.insumos, name="index-insumos"),
    path('editar-insumos/<int:id>', views.editar_insumos, name="editar-insumos"),
]