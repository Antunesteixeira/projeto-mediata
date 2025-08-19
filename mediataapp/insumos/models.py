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

    UNIDADE_MEDIDA_CHOICES = [
    ('UN', 'Unidade'),
    ('PC', 'Peça'),
    ('CJ', 'Conjunto'),
    ('PAR', 'Par'),
    ('DZ', 'Dúzia'),

    ('KG', 'Quilograma'),
    ('G', 'Grama'),
    ('MG', 'Miligrama'),
    ('T', 'Tonelada'),

    ('L', 'Litro'),
    ('ML', 'Mililitro'),
    ('M3', 'Metro cúbico'),

    ('M', 'Metro'),
    ('CM', 'Centímetro'),
    ('MM', 'Milímetro'),
    ('KM', 'Quilômetro'),

    ('M2', 'Metro quadrado'),
    ('CM2', 'Centímetro quadrado'),
    ('HA', 'Hectare'),

    ('CX', 'Caixa'),
    ('SC', 'Saca'),
    ('ROLO', 'Rolo'),
    ('BALDE', 'Balde'),
    ('TUBO', 'Tubo'),
]


    insumo = models.CharField(max_length=255)
    codigo = models.CharField(max_length=9, unique=True, blank=True)
    tipo = models.CharField(max_length=1, choices=TIPO_CHOISES)
    unidade = models.CharField(max_length=5, choices=UNIDADE_MEDIDA_CHOICES, blank=True, null=True)
    valor_unit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quant = models.IntegerField(null=True, blank=True, default=1)

    def __str__(self):
        return self.insumo

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = self._generate_unique_codigo()
        super().save(*args, **kwargs)

    def _generate_unique_codigo(self):
        while True:
            numero = f"{random.randint(0, 9999):04d}"  # número com 4 dígitos
            codigo = f"INS{numero}"  # adiciona prefixo INS
            if not Insumos.objects.filter(codigo=codigo).exists():
                return codigo

