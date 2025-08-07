# usuarios/roles.py
from rolepermissions.roles import AbstractUserRole

class Gerente(AbstractUserRole):
    available_permissions = {
        'criar_ticket': True,
        'ver_ticket': True,
    }

class Operador(AbstractUserRole):
    available_permissions = {
        'criar_ticket': True,
        'ver_ticket': True,
    }
