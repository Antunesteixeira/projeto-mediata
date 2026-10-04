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
        ('10M', '10 Metros (10M)'),
        ('18L', '18 Litros (18L)'),
        ('200KG', '200 Quilogramas (200KG)'),
        ('310ML', '310 Mililitros (310ML)'),
        ('50KG', '50 Quilogramas (50KG)'),
        ('AS', 'Atividade semanal (AS)'),
        ('BALDE', 'Balde (BALDE)'),
        ('BD', 'Balde (BD)'),
        ('BARRA', 'Barra (BARRA)'),
        ('CX', 'Caixa (CX)'),
        ('CM', 'Centímetro (CM)'),
        ('CM2', 'Centímetro quadrado (CM2)'),
        ('CENTO', 'Cento (CENTO)'),
        ('CJ', 'Conjunto (CJ)'),
        ('CHI', 'Custos horários improdutivos (CHI)'),
        ('CHP', 'Custos horários produtivos (CHP)'),
        ('DM3', 'Decímetro cúbico (DM3)'),
        ('DIA', 'Dia (DIA)'),
        ('DZ', 'Dúzia (DZ)'),
        ('FL', 'Folha (FL)'),
        ('GL', 'Galão (GL)'),
        ('G', 'Grama (G)'),
        ('HA', 'Hectare (HA)'),
        ('H', 'Hora (H)'),
        ('JG', 'Jogo (JG)'),
        ('LT', 'Latão (LT)'),
        ('L', 'Litro (L)'),
        ('MES', 'Mês (MES)'),
        ('M', 'Metro (M)'),
        ('M3', 'Metro cúbico (M3)'),
        ('M3XKM', 'Metro cúbico x quilômetro (M3XKM)'),
        ('M/MES', 'Metro por mês (M/MES)'),
        ('M2', 'Metro quadrado (M2)'),
        ('M2/MES', 'Metro quadrado por mês (M2/MES)'),
        ('MG', 'Miligrama (MG)'),
        ('MIL', 'Milheiro (MIL)'),
        ('ML', 'Mililitro (ML)'),
        ('MM', 'Milímetro (MM)'),
        # PC e SC mantêm o significado dos cadastros existentes.
        ('PCT', 'Pacote (PCT)'),
        ('PAR', 'Par (PAR)'),
        ('PC', 'Peça (PC)'),
        ('PÇ', 'Peça (PÇ)'),
        ('pp.', 'Porcentagem (pp.)'),
        ('KG', 'Quilograma (KG)'),
        ('KM', 'Quilômetro (KM)'),
        ('KW/H', 'Quilowatt por hora (KW/H)'),
        ('RL', 'Rolo (RL)'),
        ('ROLO', 'Rolo (ROLO)'),
        ('SC', 'Saca (SC)'),
        ('SACO', 'Saco (SACO)'),
        ('SC25KG', 'Saco de 25 Quilogramas (SC25KG)'),
        ('S', 'Serviço (S)'),
        ('T', 'Tonelada (T)'),
        ('T/KM', 'Tonelada por quilômetro (T/KM)'),
        ('TXKM', 'Tonelada x quilômetro (TXKM)'),
        ('TUBO', 'Tubo (TUBO)'),
        ('UN', 'Unidade (UN)'),
        ('VB', 'Valor base (VB)'),
        ('VG', 'Valor global (VG)'),
        ('V', 'Vara (V)'),
    ]


    insumo = models.CharField(max_length=255)
    codigo = models.CharField(max_length=9, unique=True, blank=True)
    tipo = models.CharField(max_length=1, choices=TIPO_CHOISES)
    unidade = models.CharField(max_length=6, choices=UNIDADE_MEDIDA_CHOICES, blank=True, null=True)
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
