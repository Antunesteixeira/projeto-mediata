#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

compose() {
  docker --context default compose --progress plain -p mediata-local -f docker-compose.local.yml "$@"
}

prepare() {
  command -v docker >/dev/null || { echo "Instale Docker com Docker Compose antes de continuar." >&2; exit 1; }
  docker --context default compose version >/dev/null
  docker --context default info >/dev/null
  if [[ ! -f dotenv_files/.env.dev ]]; then
    local task_secret task_password task_admin_password
    task_secret=$(docker --context default run --rm python:3.12-alpine python -c 'import secrets; print(secrets.token_hex(32))')
    task_password=$(docker --context default run --rm python:3.12-alpine python -c 'import secrets; print(secrets.token_hex(24))')
    task_admin_password=$(docker --context default run --rm python:3.12-alpine python -c 'import secrets; print(secrets.token_hex(16))')
    (umask 077; sed -e "s/__SECRET_KEY__/$task_secret/" -e "s/__DB_PASSWORD__/$task_password/" -e "s/__ADMIN_PASSWORD__/$task_admin_password/" dotenv_files/.env.dev.example > dotenv_files/.env.dev)
    echo "Configuração criada em dotenv_files/.env.dev (credenciais locais)."
  fi
}

case "${1:-help}" in
  setup)
    prepare
    compose up -d --build --wait --wait-timeout 180
    compose exec -T mediataapp python manage.py shell -c 'import os; from django.contrib.auth import get_user_model; User = get_user_model(); name = os.environ.get("DJANGO_SUPERUSER_USERNAME"); password = os.environ.get("DJANGO_SUPERUSER_PASSWORD"); User.objects.create_superuser(username=name, email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""), password=password) if name and password and not User.objects.filter(username=name).exists() else None'
    echo "Aplicação pronta: http://localhost:8000 — credenciais em dotenv_files/.env.dev"
    ;;
  prepare) prepare ;;
  up) prepare; compose "$@" ;;
  help|--help|-h)
    echo "Uso: ./local.sh setup | prepare | up -d | ps | logs -f mediataapp | stop | start"
    echo "Comandos Django: ./local.sh exec mediataapp python manage.py <comando>"
    ;;
  *) compose "$@" ;;
esac
