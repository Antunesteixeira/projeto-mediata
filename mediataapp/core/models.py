# models.py
from django.db import models
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

class Empresa(models.Model):
    class TipoEmpresa(models.TextChoices):
        MEI = 'MEI', _('Microempreendedor Individual')
        LTDA = 'LTDA', _('Sociedade Limitada')
        SA = 'SA', _('Sociedade Anônima')
        EIRELI = 'EIRELI', _('Empresa Individual')
        OUTRO = 'OUTRO', _('Outro')

    # Informações básicas
    nome_fantasia = models.CharField(_('Nome Fantasia'), max_length=200)
    razao_social = models.CharField(_('Razão Social'), max_length=200)
    cnpj = models.CharField(
        _('CNPJ'),
        max_length=18,
        unique=True,
        validators=[RegexValidator(
            regex=r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$',
            message='CNPJ deve estar no formato: 00.000.000/0000-00'
        )]
    )
    tipo_empresa = models.CharField(
        _('Tipo de Empresa'),
        max_length=10,
        choices=TipoEmpresa.choices,
        default=TipoEmpresa.LTDA
    )
    
    # Informações de contato
    email = models.EmailField(_('E-mail'), max_length=100)
    telefone = models.CharField(
        _('Telefone'),
        max_length=15,
        validators=[RegexValidator(
            regex=r'^\(\d{2}\) \d{4,5}-\d{4}$',
            message='Telefone deve estar no formato: (00) 00000-0000'
        )]
    )
    whatsapp = models.CharField(
        _('WhatsApp'),
        max_length=15,
        blank=True,
        null=True
    )
    
    # Endereço
    cep = models.CharField(_('CEP'), max_length=9)
    endereco = models.CharField(_('Endereço'), max_length=200)
    numero = models.CharField(_('Número'), max_length=10)
    complemento = models.CharField(_('Complemento'), max_length=100, blank=True)
    bairro = models.CharField(_('Bairro'), max_length=100)
    cidade = models.CharField(_('Cidade'), max_length=100)
    estado = models.CharField(_('Estado'), max_length=2)
    
    # Informações adicionais
    data_fundacao = models.DateField(_('Data de Fundação'), blank=True, null=True)
    descricao = models.TextField(_('Descrição da Empresa'), blank=True)
    missao = models.TextField(_('Missão'), blank=True)
    visao = models.TextField(_('Visão'), blank=True)
    valores = models.TextField(_('Valores'), blank=True)
    
    # Redes sociais
    website = models.URLField(_('Website'), blank=True)
    facebook = models.URLField(_('Facebook'), blank=True)
    instagram = models.URLField(_('Instagram'), blank=True)
    linkedin = models.URLField(_('LinkedIn'), blank=True)
    twitter = models.URLField(_('Twitter'), blank=True)
    
    # Configurações
    ativo = models.BooleanField(_('Ativo'), default=True)
    data_criacao = models.DateTimeField(_('Data de Criação'), auto_now_add=True)
    data_atualizacao = models.DateTimeField(_('Última Atualização'), auto_now=True)

    class Meta:
        verbose_name = _('Empresa')
        verbose_name_plural = _('Empresas')
        ordering = ['nome_fantasia']

    def __str__(self):
        return self.nome_fantasia

    @property
    def endereco_completo(self):
        return f"{self.endereco}, {self.numero} - {self.bairro}, {self.cidade} - {self.estado}"
    
class HorarioFuncionamento(models.Model):
    class DiasSemana(models.TextChoices):
        SEGUNDA = 'SEG', _('Segunda-feira')
        TERCA = 'TER', _('Terça-feira')
        QUARTA = 'QUA', _('Quarta-feira')
        QUINTA = 'QUI', _('Quinta-feira')
        SEXTA = 'SEX', _('Sexta-feira')
        SABADO = 'SAB', _('Sábado')
        DOMINGO = 'DOM', _('Domingo')

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='horarios_funcionamento'
    )
    dia_semana = models.CharField(
        _('Dia da Semana'),
        max_length=3,
        choices=DiasSemana.choices
    )
    abre_as = models.TimeField(_('Abre às'), blank=True, null=True)
    fecha_as = models.TimeField(_('Fecha às'), blank=True, null=True)
    fechado = models.BooleanField(_('Fechado'), default=False)

    class Meta:
        verbose_name = _('Horário de Funcionamento')
        verbose_name_plural = _('Horários de Funcionamento')
        unique_together = ['empresa', 'dia_semana']
        ordering = ['dia_semana']

    def __str__(self):
        if self.fechado:
            return f"{self.get_dia_semana_display()} - Fechado"
        return f"{self.get_dia_semana_display()} - {self.abre_as} às {self.fecha_as}"
    
class Funcionario(models.Model):
    class Cargo(models.TextChoices):
        CEO = 'CEO', _('CEO/Diretor')
        GERENTE = 'GER', _('Gerente')
        SUPERVISOR = 'SUP', _('Supervisor')
        ANALISTA = 'ANA', _('Analista')
        ASSISTENTE = 'ASS', _('Assistente')
        ESTAGIARIO = 'EST', _('Estagiário')
        OUTRO = 'OUT', _('Outro')

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='funcionarios'
    )
    nome = models.CharField(_('Nome Completo'), max_length=200)
    cargo = models.CharField(
        _('Cargo'),
        max_length=3,
        choices=Cargo.choices,
        default=Cargo.OUTRO
    )
    email = models.EmailField(_('E-mail'), max_length=100, blank=True)
    telefone = models.CharField(_('Telefone'), max_length=15, blank=True)
    foto = models.ImageField(
        _('Foto'),
        upload_to='funcionarios/',
        blank=True,
        null=True
    )
    descricao = models.TextField(_('Descrição/Cargo Detalhado'), blank=True)
    ordem_exibicao = models.IntegerField(_('Ordem de Exibição'), default=0)
    ativo = models.BooleanField(_('Ativo'), default=True)
    data_admissao = models.DateField(_('Data de Admissão'), blank=True, null=True)

    class Meta:
        verbose_name = _('Funcionário')
        verbose_name_plural = _('Funcionários')
        ordering = ['ordem_exibicao', 'nome']

    def __str__(self):
        return f"{self.nome} - {self.get_cargo_display()}"
    
class Servico(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='servicos'
    )
    nome = models.CharField(_('Nome do Serviço'), max_length=200)
    descricao = models.TextField(_('Descrição'))
    icone = models.CharField(
        _('Ícone'),
        max_length=50,
        help_text=_('Classe do ícone (ex: fas fa-cog, bi bi-gear)'),
        blank=True
    )
    imagem = models.ImageField(
        _('Imagem'),
        upload_to='servicos/',
        blank=True,
        null=True
    )
    ordem_exibicao = models.IntegerField(_('Ordem de Exibição'), default=0)
    ativo = models.BooleanField(_('Ativo'), default=True)

    class Meta:
        verbose_name = _('Serviço')
        verbose_name_plural = _('Serviços')
        ordering = ['ordem_exibicao', 'nome']

    def __str__(self):
        return self.nome