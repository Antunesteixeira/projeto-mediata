#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
TLS_ENV_FILE=${TLS_ENV_FILE:-/etc/mediata/tls.env}
if [[ -f "$TLS_ENV_FILE" ]]; then
  # Arquivo administrado por root; também funciona fora do systemd.
  source "$TLS_ENV_FILE"
fi
TLS_PROJECT_DIR=${TLS_PROJECT_DIR:-/home/antuneszi/projeto-mediata}
TLS_CERT_NAME=${TLS_CERT_NAME:-mediatanordeste.com.br-0001}
TLS_CERTBOT_CONTAINER=${TLS_CERTBOT_CONTAINER:-certbot_prod}
TLS_NGINX_CONTAINER=${TLS_NGINX_CONTAINER:-nginx_prod}
TLS_DOMAINS=${TLS_DOMAINS:-"mediatanordeste.com.br www.mediatanordeste.com.br"}
TLS_CHECK_SCRIPT=${TLS_CHECK_SCRIPT:-$SCRIPT_DIR/check-tls.py}
TLS_LOCK_FILE=${TLS_LOCK_FILE:-/run/lock/mediata-tls-renewal.lock}
read -r -a domains <<< "$TLS_DOMAINS"
certificate="$TLS_PROJECT_DIR/certbot/conf/live/$TLS_CERT_NAME/fullchain.pem"
mode=${1:-renew}
case "$mode" in
  renew|--check|--dry-run) ;;
  *) echo 'Uso: renew-tls.sh [--check|--dry-run]' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo 'Argumentos inesperados' >&2; exit 2; }

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
check_args=(--connect 127.0.0.1 --expected-certificate "$certificate")
for domain in "${domains[@]}"; do
  [[ "$domain" =~ ^[a-zA-Z0-9.-]+$ ]] || { log 'ERROR: domínio inválido'; exit 2; }
  check_args+=(--host "$domain")
done
[[ -r "$certificate" && -f "$TLS_CHECK_SCRIPT" ]] || { log 'ERROR: certificado ou verificador ausente'; exit 2; }
if [[ "$mode" == --check ]]; then
  exec python3 "$TLS_CHECK_SCRIPT" "${check_args[@]}"
fi

exec 9>"$TLS_LOCK_FILE"
flock -w 30 9 || { log 'ERROR: outra execução de renovação está em andamento'; exit 2; }
probe_file=''
status_file=$(mktemp)
cleanup() {
  local result=$?
  [[ -z "$probe_file" ]] || rm -f -- "$probe_file"
  rm -f -- "$status_file"
  if (( result != 0 )); then log "ERROR: rotina TLS terminou com código $result"; fi
}
trap cleanup EXIT

for container in "$TLS_CERTBOT_CONTAINER" "$TLS_NGINX_CONTAINER"; do
  [[ "$(docker inspect --format '{{.State.Running}}' "$container")" == true ]] || {
    log "ERROR: contêiner $container não está em execução"; exit 2;
  }
done
renewal_config="$TLS_PROJECT_DIR/certbot/conf/renewal/$TLS_CERT_NAME.conf"
grep -Eq '^authenticator[[:space:]]*=[[:space:]]*webroot[[:space:]]*$' "$renewal_config" || {
  log 'ERROR: a renovação deve usar webroot'; exit 2;
}
docker exec "$TLS_NGINX_CONTAINER" nginx -t

# Confirma o volume HTTP utilizado pelo desafio sem redirecionar para HTTPS.
challenge_dir="$TLS_PROJECT_DIR/certbot/www/.well-known/acme-challenge"
install -d -m 755 "$challenge_dir"
probe_file=$(mktemp "$challenge_dir/mediata-check-XXXXXXXX")
probe_value=$(basename -- "$probe_file")
printf '%s' "$probe_value" > "$probe_file"
chmod 644 "$probe_file"
for domain in "${domains[@]}"; do
  response=$(curl --fail --silent --show-error --max-time 15 \
    --resolve "$domain:80:127.0.0.1" "http://$domain/.well-known/acme-challenge/$probe_value")
  [[ "$response" == "$probe_value" ]] || { log "ERROR: webroot HTTP incorreto para $domain"; exit 2; }
done
rm -f -- "$probe_file"
probe_file=''

certbot_args=(renew --cert-name "$TLS_CERT_NAME" --non-interactive --no-random-sleep-on-renew)
if [[ "$mode" == --dry-run ]]; then
  certbot_args+=(--dry-run --server https://acme-staging-v02.api.letsencrypt.org/directory)
fi
renewal_failed=0
if ! docker exec "$TLS_CERTBOT_CONTAINER" certbot "${certbot_args[@]}"; then
  log 'ERROR: Certbot não concluiu a renovação'
  renewal_failed=1
fi

# A recarga também recupera uma renovação anterior ainda não ativada.
docker exec "$TLS_NGINX_CONTAINER" nginx -t
docker exec "$TLS_NGINX_CONTAINER" nginx -s reload
verified=0
for attempt in {1..12}; do
  check_result=0
  python3 "$TLS_CHECK_SCRIPT" "${check_args[@]}" > "$status_file" || check_result=$?
  if (( check_result <= 1 )); then
    cat "$status_file"
    (( check_result == 0 )) || log 'WARNING: certificado vence em menos de 30 dias'
    verified=1
    break
  fi
  (( attempt == 12 )) || sleep 2
done
if (( verified == 0 )); then
  cat "$status_file"
  log 'ERROR: Nginx não serve um certificado válido igual ao arquivo atualizado'
  exit 2
fi
(( renewal_failed == 0 )) || exit 2
log "SUCCESS: TLS verificado para ${domains[*]} ($mode)"
