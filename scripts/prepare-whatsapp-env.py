"""Cria o ambiente WhatsApp sem sobrescrever credenciais existentes."""
import os
from pathlib import Path
import secrets

mode = os.environ.get('EVOLUTION_MODE', 'development')
if mode not in {'development', 'production'}:
    raise SystemExit('Modo de configuração inválido.')
target = Path('/config/.env.whatsapp')
if target.exists():
    lines = target.read_text().splitlines()
    saved_mode = next((line.partition('=')[2] for line in lines if line.startswith('EVOLUTION_MODE=')), '')
    if saved_mode != mode:
        raise SystemExit('O arquivo existente pertence a outro ambiente. Separe os diretórios de desenvolvimento e produção.')
    print('Configuração WhatsApp existente preservada.')
else:
    values = {
        'EVOLUTION_MODE': mode,
        'EVOLUTION_ENABLED': 'true',
        'EVOLUTION_API_URL': 'http://evolution-api:8080',
        'EVOLUTION_API_KEY': secrets.token_hex(32),
        'EVOLUTION_DB_PASSWORD': secrets.token_hex(32),
        'EVOLUTION_WEBHOOK_BASE_URL': (
            'https://mediatanordeste.com.br' if mode == 'production' else 'http://mediataapp:8000'
        ),
        'EVOLUTION_API_TIMEOUT': '10',
        'EVOLUTION_DOCKER_NETWORK': (
            'projeto-mediata_mediata-network' if mode == 'production' else 'mediata-local_default'
        ),
        'EVOLUTION_MEMORY_LIMIT': '768m',
    }
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write('\n'.join(f'{key}={value}' for key, value in values.items()) + '\n')
    print('Configuração criada em dotenv_files/.env.whatsapp, sem exibir as credenciais.')
