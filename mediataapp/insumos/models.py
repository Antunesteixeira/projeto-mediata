from django.db import models

# Create your models here.
import random
from django.db import models

class Insumos(models.Model):
    TIPO_CHOISES = [
        ('S', 'Serviço'), 
        ('M', 'Material'),
        ('O', 'Mão de Obra'), 
        ('E', 'Equipamento'),
        ('T', 'Taxa'),
    ]

    insumo = models.CharField(max_length=255)
    codigo = models.CharField(max_length=6, unique=True, blank=True)
    tipo = models.CharField(max_length=1, choices=TIPO_CHOISES)
    valor_unit = models.DecimalField(max_digits=10, decimal_places=2)
    quant = models.IntegerField(null=True, blank=True, default=1)

    def __str__(self):
        return self.insumo

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = self._generate_unique_codigo()
        super().save(*args, **kwargs)

    def _generate_unique_codigo(self):
        while True:
            codigo = f"{random.randint(0, 999999):06d}"  # gera número com 6 dígitos
            if not Insumos.objects.filter(codigo=codigo).exists():
                return codigo
