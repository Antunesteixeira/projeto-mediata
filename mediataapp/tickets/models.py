from django.db import models, router, transaction
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from insumos.models import Insumos

from clientes.models import Cliente
from colaborador.models import Colaborador

class SequenciaTicket(models.Model):
    prefixo = models.CharField(max_length=4, primary_key=True)
    ultimo_numero = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ultimo_numero__lte=999),
                name='sequencia_ticket_limite_999',
            ),
        ]


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

    ticket = models.CharField(max_length=10, unique=True, blank=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    empresa = models.ForeignKey(
        'core.Empresa', on_delete=models.PROTECT, null=True, blank=True,
        related_name='tickets',
    )
    assumido_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tickets_assumidos',
    )
    assumido_em = models.DateTimeField(null=True, blank=True)
    colaborador = models.ForeignKey(Colaborador, on_delete=models.SET_NULL, null=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='L')
    emergencial = models.BooleanField(default=False)
    descricao = models.TextField()
    valor_material = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0) # Foi criado um novo modelo para calcular essas informaçoes
    valor_mao_obra = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0) # Foi criado um novo modelo para calcular essas informaçoes
    valor_custo = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0) # Foi criado um novo modelo para calcular essas informaçoes
    valor_faturamento = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=1) # Foi criado um novo modelo para calcular essas informaçoes
    valor_equipamento = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, null=True) # Add no banco de dados 
    data_criacao = models.DateTimeField(auto_now_add=True)
    ultimo_update = models.DateField(auto_now_add=True)
    finalizado = models.BooleanField(default=False, null=True) 
    data_finalizar = models.DateField(null=True, blank=True)
    key = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    nfe_path = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['-data_criacao']

    def validate_unique(self, exclude=None):
        if not str(self.ticket or '').strip():
            exclude = set(exclude or ()) | {'ticket'}
        return super().validate_unique(exclude=exclude)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        using = using or router.db_for_write(type(self), instance=self)
        if self._state.adding and self.empresa_id is None and self.usuario_id:
            from core.tenancy import empresa_do_usuario

            empresa = empresa_do_usuario(self.usuario)
            if empresa is not None:
                self.empresa = empresa
        if update_fields is not None:
            update_fields = frozenset(update_fields)
        save_options = {
            'force_insert': force_insert, 'force_update': force_update,
            'using': using, 'update_fields': update_fields,
        }
        if update_fields is not None and 'ticket' not in update_fields:
            return super().save(**save_options)

        from .numeracao import definir_codigo_ticket

        with transaction.atomic(using=using):
            if self.pk is not None:
                # A ordem ticket -> sequência evita ciclos entre edições concorrentes.
                atual = type(self).objects.using(using).select_for_update().filter(
                    pk=self.pk,
                ).values_list('ticket', flat=True).first()
                if not str(self.ticket or '').strip() and atual:
                    self.ticket = atual
            self.ticket = definir_codigo_ticket(self.ticket, using)
            return super().save(**save_options)
    
    def func_valor_custo_total(self):
        if self.valor_faturamento == 0 and self.valor_custo == 0:
            return self.valor_mao_obra + self.valor_custo + 1
        else:
            return self.valor_mao_obra + self.valor_custo

    def func_bdi(self):
        divisor = self.func_valor_custo_total()
        if divisor == 0:
            divisor = 1  # evita divisão por zero, sem alterar atributo

        return self.valor_faturamento / divisor


    def func_finalizado(self):
        if self.status == 'F':
            self.finalizado = True
        elif self.status in ['A', 'O', 'L', 'B']: 
            self.finalizado = False
        
        return self.finalizado
    
    def __str__(self):
        return self.ticket
    
    def func_soma_margem(self):
        return self.valor_material + self.valor_mao_obra + self.valor_equipamento + self.valor_custo
    
class Orcamento(models.Model):
    orcamento = models.CharField(max_length=255)
    ticket_orcamento = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    data_criacao = models.DateTimeField(auto_now_add=True)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descricao = models.TextField()

    def __str__(self):
        return self.orcamento

class ItemOrcamento(models.Model):
    orcamento = models.ForeignKey(Orcamento, on_delete=models.SET_NULL, null=True)
    item = models.ForeignKey(Insumos, on_delete=models.SET_NULL, null=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)
    quant = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))


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
    TIPO_CHOICES = (
        ('M', 'Material'),
        ('S', 'Serviço'),
        ('O', 'Mão de Obra'),
        ('E', 'Equipamento'),
        ('T', 'Taxa'),
    )
    tipo = models.CharField(max_length=1, choices=TIPO_CHOICES)
    valor_pagamento = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor do Pagamento", null=True, blank=True)
    data_pagamento = models.DateField()
    data_update_pagamento = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    status_pagamento = models.BooleanField(default=False)
    ticket_pagamento = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="pagamentos")
    comprovante = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Pagamento {self.id} - {self.get_tipo_display()}"
    

class Anexo(models.Model):
    ticket_anexo = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to='anexos/')  # novo campo
    descricao_anexo = models.CharField(max_length=255, null=True, blank=True)
    data_upload = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.arquivo.name  # ou self.descricao_anexo

class Recebimentos(models.Model):

    TIPO_PAGAMENTO_CHOICES = (
        ('Cartão de Crédito', 'Cartão de Crédito'),
        ('Cartão de Débito', 'Cartão de Débito'),
        ('Transferência Bancária', 'Transferência Bancária'),
        ('Pix', 'Pix'),
        ('Cheque', 'Cheque'),
        ('Boleto', 'Boleto'),
        ('Outro', 'Outro'),
    )

    STATUS_RECEBIMENTO_CHOICES = (
        (True, 'Recebido'),
        (False, 'a Receber'),
    )

    FORMA_PAGAMENTO_CHOICES = (
        ('À vista', 'À vista'),
        ('A Prazo', 'A Prazo'),
    )

    razao_social = models.CharField(max_length=255, null=True, blank=True)
    numero_nota_fiscal = models.CharField(max_length=255, null=True, blank=True)
    serie_nota_fiscal = models.CharField(max_length=255, null=True, blank=True)
    data_emissao = models.DateField(null=True, blank=True)
    data_vencimento = models.DateField(null=True, blank=True)
    valor_recebimento = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status_recebimento = models.BooleanField(choices=STATUS_RECEBIMENTO_CHOICES, default=False)
    ticket_recebimento = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="recebimentos")
    descricao_recebimento = models.CharField(max_length=255, null=True, blank=True)
    forma_pagamento = models.CharField(max_length=30, choices=FORMA_PAGAMENTO_CHOICES, null=True, blank=True)
    tipo_pagamento = models.CharField(max_length=30, choices=TIPO_PAGAMENTO_CHOICES, null=True, blank=True)
    comprovante_recebimento = models.CharField(max_length=255, null=True, blank=True)
    data_recebimento = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    recebimento_realizado = models.BooleanField(default=False)
    data_recebimento_realizado = models.DateTimeField(null=True, blank=True)
