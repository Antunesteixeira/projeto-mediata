"""Fixtures explícitas de empresa para os testes, sem sinais automáticos."""

from core.models import Empresa
from .models import UsuarioEmpresa


def criar_empresa(nome='Empresa fictícia A', cnpj='00.000.000/0000-01', ativa=True):
    return Empresa.objects.create(
        nome_fantasia=nome, razao_social=f'{nome} LTDA', cnpj=cnpj,
        email='empresa@example.invalid', telefone='(00) 00000-0000',
        cep='00000-000', endereco='Rua fictícia', numero='1',
        bairro='Bairro fictício', cidade='Cidade fictícia', estado='PE', ativo=ativa,
    )


def vincular_usuario(usuario, empresa):
    return UsuarioEmpresa.objects.create(usuario=usuario, empresa=empresa)
