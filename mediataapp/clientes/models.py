from django.db import models

class Cliente(models.Model):
    TIPO_PESSOA_CHOICES = [
        ('F', 'Pessoa Física'),
        ('J', 'Pessoa Jurídica'),
    ]

    tipo_pessoa = models.CharField(max_length=1, choices=TIPO_PESSOA_CHOICES, default='F')
    nome_razao_social = models.CharField("Nome / Razão Social", max_length=150)
    sobrenome_nome_fantasia = models.CharField("Sobrenome / Nome Fantasia", max_length=150, blank=True, null=True)

    cpf_cnpj = models.CharField("CPF / CNPJ", max_length=18, unique=True)
    rg_ie = models.CharField("RG / Inscrição Estadual", max_length=20, blank=True, null=True)

    email = models.EmailField("E-mail", max_length=100, blank=True, null=True)
    telefone = models.CharField("Telefone", max_length=20, blank=True, null=True)
    celular = models.CharField("Celular", max_length=20, blank=True, null=True)

    cep = models.CharField("CEP", max_length=9, blank=True, null=True)
    endereco = models.CharField("Endereço", max_length=200, blank=True, null=True)
    numero = models.CharField("Número", max_length=10, blank=True, null=True)
    complemento = models.CharField("Complemento", max_length=100, blank=True, null=True)
    bairro = models.CharField("Bairro", max_length=100, blank=True, null=True)
    cidade = models.CharField("Cidade", max_length=100, blank=True, null=True)
    estado = models.CharField("Estado", max_length=2, blank=True, null=True)

    ativo = models.BooleanField(default=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome_razao_social
