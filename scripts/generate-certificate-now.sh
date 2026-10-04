#!/usr/bin/env bash
set -euo pipefail

echo 'A geração legada foi substituída pela rotina de renovação TLS.' >&2
echo 'Teste: sudo /usr/local/lib/mediata/renew-tls.sh --dry-run' >&2
echo 'Renovação: sudo systemctl start mediata-tls-renewal.service' >&2
echo 'Instalação: sudo ./scripts/install-tls-renewal.sh --project-dir /home/antuneszi/projeto-mediata' >&2
exit 1
