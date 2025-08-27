#! /bin/sh

set -e  # para execução se algum comando falhar

echo "🚀 Iniciando script de inicialização do container..."

# 🔹 Espera pelo Postgres
while ! nc -z $POSTGRES_HOST $POSTGRES_PORT; do
  echo "🟡 Aguardando Postgres ($POSTGRES_HOST:$POSTGRES_PORT)..."
  sleep 2
done

echo "✅ Postgres disponível em $POSTGRES_HOST:$POSTGRES_PORT"

# 🔹 Apenas em produção: coleta estáticos
if [ "$ENVIRONMENT" = "production" ]; then
  echo "📦 Coletando arquivos estáticos..."
  python manage.py collectstatic --noinput
fi

# 🔹 Sempre aplica migrações
echo "🗄️ Aplicando migrações..."
python manage.py migrate --noinput

# 🔹 Decide modo de execução
if [ "$ENVIRONMENT" = "production" ]; then
  echo "🚀 Iniciando Gunicorn (modo produção)..."
  exec gunicorn mediata.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers ${GUNICORN_WORKERS:-4} \
      --threads ${GUNICORN_THREADS:-4} \
      --timeout ${GUNICORN_TIMEOUT:-120}
else
  echo "🟢 Iniciando Django Runserver (modo desenvolvimento)..."
  exec python manage.py runserver 0.0.0.0:8000
fi
