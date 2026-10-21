from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class LancamentoManual(models.Model):
    class Operacao(models.TextChoices):
        CREDITO = 'credito', 'Crédito'
        DEBITO = 'debito', 'Débito'

    empresa = models.ForeignKey(
        'core.Empresa',
        on_delete=models.PROTECT,
        related_name='lancamentos_financeiros_manuais',
        verbose_name='Empresa',
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        editable=False,
        verbose_name='Criado por',
    )
    operacao = models.CharField('Operação', max_length=7, choices=Operacao.choices)
    descricao = models.CharField('Descrição', max_length=255)
    contraparte = models.CharField(
        'Cliente/Favorecido', max_length=255, blank=True, default='',
    )
    valor = models.DecimalField(
        'Valor',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    data_vencimento = models.DateField('Vencimento', db_index=True)
    liquidado = models.BooleanField('Quitado', default=False)
    data_quitacao = models.DateField('Data da quitação', null=True, blank=True)
    criado_em = models.DateTimeField('Criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Lançamento manual'
        verbose_name_plural = 'Lançamentos manuais'
        ordering = ['data_vencimento', 'id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valor__gt=0),
                name='financeiro_manual_valor_positivo',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(liquidado=False, data_quitacao__isnull=True)
                    | models.Q(liquidado=True, data_quitacao__isnull=False)
                ),
                name='financeiro_manual_quitacao_coerente',
            ),
        ]

    def __str__(self):
        return self.descricao

    def clean(self):
        super().clean()
        errors = {}
        if self.liquidado:
            if self.data_quitacao is None:
                errors['data_quitacao'] = 'Informe a data da quitação.'
            elif self.data_quitacao > timezone.localdate():
                errors['data_quitacao'] = 'A data da quitação não pode ser futura.'
        elif self.data_quitacao is not None:
            errors['data_quitacao'] = (
                'Marque o lançamento como quitado ou remova a data da quitação.'
            )
        if errors:
            raise ValidationError(errors)
