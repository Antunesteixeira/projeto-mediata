from django.db import models

from django.contrib.auth.models import User

#from cliente.models import Cliente
#from colaborador.models import Colaborador

class Ticket(models.Model):
    
    STATUS_CHOICES = [
        ('O', 'Orçamento'), 
        ('A', 'Aprovado'),
        ('E', 'Executado'),         
        ('V', 'Vistoriado'),
        ('F', 'Finalizado'),
        ('R', 'Rejeitado'), 
    ]

    ticket = models.CharField(max_length=6, unique=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    #colaborador = models.ForeignKey(Colaborador, on_delete=models.SET_NULL, null=True)
    #cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='L')
    emergencial = models.BooleanField(default=False)
    descricao = models.TextField()
    valor_material = models.DecimalField(max_digits=10, decimal_places=2)
    valor_mao_obra = models.DecimalField(max_digits=10, decimal_places=2)
    valor_custo = models.DecimalField(max_digits=10, decimal_places=2)
    valor_faturamento = models.DecimalField(max_digits=10, decimal_places=2)
    data_criacao = models.DateTimeField(auto_now_add=True)
    ultimo_update = models.DateField(auto_now_add=True)
    finalizado = models.BooleanField(default=False, null=True) 
    data_finalizar = models.DateField()

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
    
    
        
       
