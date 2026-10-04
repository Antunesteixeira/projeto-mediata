#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd -- "$SCRIPT_DIR/.." && pwd)
if [[ ${1:-} == --project-dir && $# == 2 ]]; then
  project_dir=$2
elif (( $# != 0 )); then
  echo 'Uso: install-tls-renewal.sh [--project-dir /caminho/absoluto]' >&2
  exit 2
fi
[[ $EUID == 0 ]] || { echo 'Execute este instalador com sudo.' >&2; exit 2; }
[[ "$project_dir" =~ ^/[a-zA-Z0-9_./-]+$ && -d "$project_dir/certbot/conf" ]] || {
  echo 'Use um caminho absoluto sem espaços, com certificados existentes.' >&2; exit 2;
}
for command in docker systemctl systemd-analyze python3 openssl flock curl; do
  command -v "$command" >/dev/null || { echo "Comando ausente: $command" >&2; exit 2; }
done
exec 8>/run/lock/mediata-tls-install.lock
flock -n 8 || { echo 'Outro instalador TLS está em execução.' >&2; exit 2; }
if [[ -f /etc/mediata/tls.env ]]; then
  source /etc/mediata/tls.env
  [[ ${TLS_PROJECT_DIR:-} == "$project_dir" ]] || {
    echo 'TLS_PROJECT_DIR existente diverge de --project-dir; revise /etc/mediata/tls.env.' >&2; exit 2;
  }
fi
case "$(systemctl is-active mediata-tls-renewal.service 2>/dev/null || true)" in
  active|activating) echo 'Aguarde a renovação atual terminar antes de instalar.' >&2; exit 2 ;;
esac
exec 9>"${TLS_LOCK_FILE:-/run/lock/mediata-tls-renewal.lock}"
flock -n 9 || { echo 'Uma renovação TLS está em execução; tente novamente depois.' >&2; exit 2; }
for file in renew-tls.sh check-tls.py systemd/mediata-tls-renewal.service systemd/mediata-tls-renewal.timer; do
  [[ -f "$SCRIPT_DIR/$file" ]] || { echo "Arquivo ausente: $file" >&2; exit 2; }
done
[[ -r "$project_dir/certbot/conf/live/mediatanordeste.com.br-0001/fullchain.pem" ]] || {
  echo 'A linhagem mediatanordeste.com.br-0001 deve existir antes da instalação.' >&2; exit 2;
}
for container in nginx_prod certbot_prod; do
  [[ "$(docker inspect --format '{{.State.Running}}' "$container")" == true ]] || {
    echo "Contêiner indisponível: $container" >&2; exit 2;
  }
done

install -d -m 700 /var/backups/mediata-tls
backup_dir=$(mktemp -d /var/backups/mediata-tls/transition-XXXXXXXX)
declare -A files=(
  [renew-tls.sh]=/usr/local/lib/mediata/renew-tls.sh
  [check-tls.py]=/usr/local/lib/mediata/check-tls.py
  [tls.env]=/etc/mediata/tls.env
  [service]=/etc/systemd/system/mediata-tls-renewal.service
  [timer]=/etc/systemd/system/mediata-tls-renewal.timer
)
for key in "${!files[@]}"; do
  [[ ! -f "${files[$key]}" ]] || cp -a -- "${files[$key]}" "$backup_dir/$key"
done
timer_enabled=$(systemctl is-enabled mediata-tls-renewal.timer 2>/dev/null || true)
timer_active=$(systemctl is-active mediata-tls-renewal.timer 2>/dev/null || true)
legacy_enabled=$(systemctl is-enabled certbot.timer 2>/dev/null || true)
legacy_active=$(systemctl is-active certbot.timer 2>/dev/null || true)
legacy_container=''
executor_changed=0
printf 'legacy_timer_enabled=%s\nlegacy_timer_active=%s\n' "$legacy_enabled" "$legacy_active" > "$backup_dir/state.txt"

rollback() {
  local result=$?
  (( result != 0 )) || return 0
  trap - EXIT
  set +e
  echo "Falha na instalação; restaurando a configuração anterior. Backup: $backup_dir" >&2
  systemctl stop mediata-tls-renewal.timer mediata-tls-renewal.service
  systemctl disable mediata-tls-renewal.timer
  for key in "${!files[@]}"; do
    if [[ -f "$backup_dir/$key" ]]; then
      cp -a -- "$backup_dir/$key" "${files[$key]}"
    else
      rm -f -- "${files[$key]}"
    fi
  done
  if [[ -n "$legacy_container" ]]; then
    docker rm -f certbot_prod >/dev/null 2>&1
    docker rename "$legacy_container" certbot_prod
    docker update --restart=unless-stopped certbot_prod >/dev/null
    docker start certbot_prod >/dev/null
  elif (( executor_changed == 1 )); then
    docker update --restart=unless-stopped certbot_prod >/dev/null
    docker start certbot_prod >/dev/null
  fi
  systemctl daemon-reload
  [[ "$timer_enabled" != enabled ]] || systemctl enable mediata-tls-renewal.timer
  [[ "$timer_active" != active ]] || systemctl start mediata-tls-renewal.timer
  [[ "$legacy_enabled" != enabled ]] || systemctl enable certbot.timer
  [[ "$legacy_active" != active ]] || systemctl start certbot.timer
  exit "$result"
}
if [[ "$timer_active" == active ]]; then
  systemctl stop mediata-tls-renewal.timer
fi
case "$(systemctl is-active mediata-tls-renewal.service 2>/dev/null || true)" in
  active|activating)
    [[ "$timer_active" != active ]] || systemctl start mediata-tls-renewal.timer
    echo 'Aguarde a renovação atual terminar antes de instalar.' >&2
    exit 2
    ;;
esac
trap rollback EXIT

install -d -m 755 /usr/local/lib/mediata
install -d -m 700 /etc/mediata
install -m 755 "$SCRIPT_DIR/renew-tls.sh" /usr/local/lib/mediata/renew-tls.sh
install -m 755 "$SCRIPT_DIR/check-tls.py" /usr/local/lib/mediata/check-tls.py
if [[ ! -f /etc/mediata/tls.env ]]; then
  printf 'TLS_PROJECT_DIR="%s"\nTLS_CERT_NAME=mediatanordeste.com.br-0001\nTLS_CERTBOT_CONTAINER=certbot_prod\nTLS_NGINX_CONTAINER=nginx_prod\nTLS_DOMAINS="mediatanordeste.com.br www.mediatanordeste.com.br"\n' \
    "$project_dir" > /etc/mediata/tls.env
  chmod 600 /etc/mediata/tls.env
fi
install -m 644 "$SCRIPT_DIR/systemd/mediata-tls-renewal.service" /etc/systemd/system/mediata-tls-renewal.service
install -m 644 "$SCRIPT_DIR/systemd/mediata-tls-renewal.timer" /etc/systemd/system/mediata-tls-renewal.timer
systemd-analyze verify /etc/systemd/system/mediata-tls-renewal.service /etc/systemd/system/mediata-tls-renewal.timer

# Mantém a imagem e os volumes existentes; somente o executor Certbot muda.
if docker inspect --format '{{json .Config.Entrypoint}}' certbot_prod | grep -q 'certbot renew'; then
  image=$(docker inspect --format '{{.Image}}' certbot_prod)
  network=$(docker inspect --format '{{.HostConfig.NetworkMode}}' certbot_prod)
  container_backup_name="certbot_prod-legacy-$(date -u +%Y%m%d%H%M%S)"
  executor_changed=1
  docker update --restart=no certbot_prod >/dev/null
  docker stop certbot_prod >/dev/null
  docker rename certbot_prod "$container_backup_name"
  legacy_container=$container_backup_name
  printf 'legacy_container=%s\n' "$legacy_container" >> "$backup_dir/state.txt"
  docker run -d --name certbot_prod --restart unless-stopped --network "$network" \
    --volumes-from "$legacy_container" --entrypoint /bin/sh "$image" \
    -c 'trap "exit 0" TERM INT; while :; do sleep 3600 & wait ${!}; done' >/dev/null
fi

systemctl daemon-reload
flock -u 9
/usr/local/lib/mediata/renew-tls.sh --dry-run
systemctl start mediata-tls-renewal.service
systemctl enable --now mediata-tls-renewal.timer

# A rotina nova já foi validada antes de desativar o agendamento standalone.
if systemctl list-unit-files certbot.timer --no-legend | grep -q '^certbot.timer'; then
  systemctl disable --now certbot.timer
  systemctl reset-failed certbot.service 2>/dev/null || true
fi
trap - EXIT
printf 'Rotina TLS instalada. Backup: %s\n' "$backup_dir"
systemctl list-timers mediata-tls-renewal.timer --no-pager
