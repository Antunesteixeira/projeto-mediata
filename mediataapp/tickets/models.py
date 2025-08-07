from django.db import models
import uuid

from django.contrib.auth.models import User
from insumos.models import Insumos

from clientes.models import Cliente
#from colaborador.models import Colaborador

class Ticket(models.Model):
    
    STATUS_CHOICES = [
        ('L', 'Levantamento'),
        ('C', 'Cotação'), 
        ('A', 'Aprovado'),
        ('E', 'Em execução'),
        ('X', 'Executado'),         
        ('V', 'Vistoriado'),
        ('F', 'Finalizado'),
        ('R', 'Rejeitado'), 
    ]

    ticket = models.CharField(max_length=6, unique=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    #colaborador = models.ForeignKey(Colaborador, on_delete=models.SET_NULL, null=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='L')
    emergencial = models.BooleanField(default=False)
    descricao = models.TextField()
    valor_material = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=1) # Foi criado um novo modelo para calcular essas informaçoes
    valor_mao_obra = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=1) # Foi criado um novo modelo para calcular essas informaçoes
    valor_custo = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=1) # Foi criado um novo modelo para calcular essas informaçoes
    valor_faturamento = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=1) # Foi criado um novo modelo para calcular essas informaçoes
    # valor_equipamento = models.DecimalField(max_digits=10, decimal_places=2, blanck=True, decimal=1) Add no banco de dados 
    data_criacao = models.DateTimeField(auto_now_add=True)
    ultimo_update = models.DateField(auto_now_add=True)
    finalizado = models.BooleanField(default=False, null=True) 
    data_finalizar = models.DateField(null=True, blank=True)
    key = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        ordering = ['-data_criacao']
    
    def func_valor_custo_total(self):
        if self.valor_faturamento == 0 and self.valor_custo == 0:
            return self.valor_mao_obra + self.valor_custo + 1
        else:
            return self.valor_mao_obra + self.valor_custo
    
    def func_bdi(self):
        return self.valor_faturamento / self.func_valor_custo_total()

    def func_finalizado(self):
        if self.status == 'F':
            self.finalizado = True
        elif self.status in ['A', 'O', 'L', 'B']: 
            self.finalizado = False
        
        return self.finalizado
    
    def __str__(self):
        return self.ticket
    
class Orcamento(models.Model):
    orcamento = models.CharField(max_length=255)
    ticket_orcamento = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    data_criacao = models.DateTimeField(auto_now_add=True)
    descricao = models.TextField()

    def __str__(self):
        return self.orcamento

class ItemOrcamento(models.Model):
    orcamento = models.ForeignKey(Orcamento, on_delete=models.SET_NULL, null=True)
    item = models.ForeignKey(Insumos, on_delete=models.SET_NULL, null=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)
    quant =  models.IntegerField(default=1)


class Material(models.Model):
    material = models.CharField(max_length=255)
    orcamento_material = models.ForeignKey(Orcamento, on_delete=models.SET_NULL, null=True)
    valor_material =  models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.material
    
class Servico(models.Model):
    servico = models.CharField(max_length=255)
    orcamento_servico = models.ForeignKey(Orcamento, on_delete=models.SET_NULL, null=True)
    valor_servico = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.servico
    
class HistoricoTicket(models.Model):
    ticket_historico = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True)
    data_historico = models.DateTimeField(auto_now_add=True)
    descricao_historico = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.descricao_historico
    
class Pagamentos(models.Model):
    PAGAMENTOS_CHOICES = [
        ('M', 'Material'),
        ('O', 'Mão de Obra'), 
        ('E', 'Equipamento'),
    ]

    ticket_pagamento = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True)
    tipo = models.CharField(max_length=1, choices=PAGAMENTOS_CHOICES, blank=True, null=True)
    data_pagamento = models.DateTimeField(auto_now_add=True)
    valor_pagamento = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    status_pagamento = models.BooleanField(default=False) 


