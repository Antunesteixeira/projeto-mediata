#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

action="${1:-help}"
if [[ $# -gt 0 ]]; then shift; fi
mode=development
if [[ "${1:-}" == --production ]]; then
  mode=production
  shift
fi

prepare() {
  docker --context default info >/dev/null
  docker --context default run --rm --network none \
    --user "$(id -u):$(id -g)" \
    -e "EVOLUTION_MODE=$mode" \
    -v "$PWD/dotenv_files:/config" \
    -v "$PWD/scripts/prepare-whatsapp-env.py:/prepare.py:ro" \
    python:3.12-alpine python /prepare.py
}

compose() {
  test -f dotenv_files/.env.whatsapp || { echo 'Execute ./whatsapp.sh prepare primeiro.' >&2; exit 1; }
  docker --context default compose --progress plain \
    -p mediata-whatsapp --env-file dotenv_files/.env.whatsapp \
    -f docker-compose.whatsapp.yml "$@"
}

case "$action" in
  prepare) prepare ;;
  setup)
    prepare
    if [[ "$mode" == development ]]; then
      ./local.sh setup
    fi
    compose up -d --wait --wait-timeout 240
    if [[ "$mode" == development ]]; then
      echo 'WhatsApp disponível em http://localhost:8000/whatsapp/ para gerentes e administradores.'
    else
      echo 'Evolution disponível na rede privada. Publique/reinicie a aplicação pelo fluxo documentado para carregar a configuração.'
    fi
    ;;
  up|ps|logs|stop|start|pull) compose "$action" "$@" ;;
  help|--help|-h)
    echo 'Uso: ./whatsapp.sh setup | prepare | up -d | ps | logs | stop | start'
    echo 'Na VM: ./whatsapp.sh setup --production (mantém banco e volumes do sistema).'
    ;;
  *) echo 'Comando inválido. Use ./whatsapp.sh help.' >&2; exit 1 ;;
esac
