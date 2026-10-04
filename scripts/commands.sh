#!/bin/sh
set -e

echo "🚀 Iniciando script de inicialização do container..."

# 🔹 Configuração de timeout para espera do PostgreSQL
MAX_RETRIES=30
RETRY_COUNT=0

echo "🟡 Aguardando PostgreSQL (psql:5432)..."

# Teste de conexão corrigido
until python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect(('psql', 5432))
    s.close()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT+1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "❌ Timeout esperando por PostgreSQL após $MAX_RETRIES tentativas."
        exit 1
    fi
    echo "📡 Tentativa $RETRY_COUNT/$MAX_RETRIES - PostgreSQL não responde..."
    sleep 2
done

echo "✅ PostgreSQL disponível!"

# 🔹 Verificar se há mudanças nos modelos e criar migrações
echo "📋 Verificando mudanças nos modelos..."
if python manage.py makemigrations --dry-run --noinput | grep -q "No changes detected"; then
    echo "✅ Nenhuma mudança detectada nos modelos"
else
    echo "🔄 Criando migrações para mudanças detectadas..."
    python manage.py makemigrations --noinput
fi

# 🔹 Aplicar migrações
echo "🗄️ Aplicando migrações do banco de dados..."
python manage.py migrate --noinput
echo "✅ Migrações aplicadas com sucesso!"

# 🔹 Coletar estáticos
if [ "$ENVIRONMENT" = "production" ]; then
    echo "📦 Coletando arquivos estáticos..."
    # Preserva Bootstrap, logos e outros arquivos já existentes no volume.
    python manage.py collectstatic --noinput
    echo "✅ Arquivos estáticos coletados!"
else
    echo "📦 Pulando collectstatic (modo desenvolvimento)"
fi

# 🔹 Comando de execução
if [ "$ENVIRONMENT" = "production" ]; then
    echo "🚀 Iniciando Gunicorn (modo produção)..."
    WORKERS=${GUNICORN_WORKERS:-4}
    THREADS=${GUNICORN_THREADS:-4}
    TIMEOUT=${GUNICORN_TIMEOUT:-120}

    echo "🔧 Configuração Gunicorn: Workers=$WORKERS, Threads=$THREADS, Timeout=$TIMEOUT"

    exec gunicorn mediata.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers $WORKERS \
        --threads $THREADS \
        --timeout $TIMEOUT \
        --access-logfile - \
        --error-logfile - \
        --capture-output \
        --preload
else
    echo "🟢 Iniciando Django Runserver (modo desenvolvimento)..."
    exec python manage.py runserver 0.0.0.0:8000
fi
