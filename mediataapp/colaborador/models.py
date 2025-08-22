from django.db import models

class Colaborador(models.Model):
    # Tipo de pessoa
    TIPO_PESSOA_CHOICES = [
        ('PF', 'Pessoa Física'),
        ('PJ', 'Pessoa Jurídica'),
    ]
    tipo_pessoa = models.CharField(
        max_length=2,
        choices=TIPO_PESSOA_CHOICES,
        default='PF'
    )

    # Pessoa Física
    nome_completo = models.CharField(max_length=150, blank=True, null=True)
    cpf = models.CharField(max_length=14, blank=True, null=True, unique=True)
    data_nascimento = models.DateField(blank=True, null=True, default=None)
    funcao = models.CharField(max_length=25, blank=True, null=True)
    
    # Pessoa Jurídica
    razao_social = models.CharField(max_length=150, blank=True, null=True)
    cnpj = models.CharField(max_length=18, blank=True, null=True, unique=True)
    nome_fantasia = models.CharField(max_length=150, blank=True, null=True)

    # Contato
    email = models.EmailField(blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    endereco = models.TextField(blank=True, null=True)

    # Dados bancários
    banco = models.CharField(max_length=100, blank=True, null=True)
    agencia = models.CharField(max_length=10, blank=True, null=True)
    conta = models.CharField(max_length=20, blank=True, null=True)
    tipo_conta = models.CharField(
        max_length=20,
        choices=[
            ('corrente', 'Conta Corrente'),
            ('poupanca', 'Poupança'),
            ('salario', 'Conta Salário')
        ],
        blank=True,
        null=True
    )

    # PIX
    tipo_chave_pix = models.CharField(
        max_length=20,
        choices=[
            ('cpf', 'CPF'),
            ('cnpj', 'CNPJ'),
            ('email', 'E-mail'),
            ('telefone', 'Telefone'),
            ('aleatoria', 'Chave Aleatória'),
        ],
        blank=True,
        null=True
    )
    chave_pix = models.CharField(max_length=100, blank=True, null=True)

    # Registro
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        if self.tipo_pessoa == 'PF':
            return self.nome_completo or "Pessoa Física sem nome"
        return self.razao_social or "Pessoa Jurídica sem razão social"
