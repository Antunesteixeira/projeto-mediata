#!/bin/bash
# ============================================================
# Script Restore Backup - Recuperação de Emergência
# Use com cuidado - sobrescreve dados existentes!
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ $*${NC}"; }
log_success() { echo -e "${GREEN}✓ $*${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
log_error() { echo -e "${RED}✗ $*${NC}"; }

log_info "========================================="
log_info "Restauração de Backup - CUIDADO!"
log_info "========================================="

# Verificar argumentos
if [ -z "$1" ]; then
    log_error "Uso: ./restore-backup.sh <backup_name> [--from-gcs]"
    echo "Exemplo: ./restore-backup.sh mediata_backup_20240115_143022"
    echo "         ./restore-backup.sh mediata_backup_20240115_143022 --from-gcs"
    exit 1
fi

BACKUP_NAME="$1"
FROM_GCS="${2:---local}"
BACKUP_DIR="/backups/mediata"
DB_CONTAINER="psql_prod"

# ⚠️ CONFIRMAÇÃO DUPLA
log_warn "ATENÇÃO: Esta operação pode sobrescrever dados!"
read -p "Digite 'SIM' para confirmar restauração: " CONFIRM
if [ "$CONFIRM" != "SIM" ]; then
    log_error "Restauração cancelada"
fi

# 1. Parar aplicação
log_info "1. Parando containers..."
docker-compose -f docker-compose.prod.yml down || true

# 2. Baixar backup do GCS (se necessário)
if [ "$FROM_GCS" == "--from-gcs" ]; then
    log_info "2. Baixando backup do Google Cloud Storage..."
    mkdir -p "${BACKUP_DIR}"
    gsutil -m cp "gs://mediata-backups/${BACKUP_NAME}"* "${BACKUP_DIR}/" || \
        log_error "Falha ao baixar backup do GCS"
fi

# 3. Verificar se arquivos de backup existem
if [ ! -f "${BACKUP_DIR}/${BACKUP_NAME}_db.sql.gz" ]; then
    log_error "Arquivo de backup não encontrado: ${BACKUP_DIR}/${BACKUP_NAME}_db.sql.gz"
fi

# 4. Remover volume antigo (PERIGOSO!)
log_warn "Removendo volume antigo do PostgreSQL..."
docker volume rm pgdata_prod || true

# 5. Reiniciar containers com volume novo
log_info "3. Iniciando PostgreSQL com volume novo..."
docker-compose -f docker-compose.prod.yml up -d psql

# Aguardar PostgreSQL estar pronto
sleep 10
for i in {1..30}; do
    if docker exec "${DB_CONTAINER}" pg_isready -U "${POSTGRES_USER}" > /dev/null 2>&1; then
        log_success "PostgreSQL pronto"
        break
    fi
    if [ $i -eq 30 ]; then
        log_error "PostgreSQL não respondendo!"
    fi
    sleep 1
done

# 6. Restaurar banco de dados
log_info "4. Restaurando banco de dados..."
gunzip < "${BACKUP_DIR}/${BACKUP_NAME}_db.sql.gz" | \
    docker exec -i "${DB_CONTAINER}" psql -U "${POSTGRES_USER}" "${POSTGRES_DB}" || \
    log_error "Falha ao restaurar banco de dados"

log_success "Banco de dados restaurado"

# 7. Restaurar arquivos (se existir)
if [ -f "${BACKUP_DIR}/${BACKUP_NAME}_files.tar.gz" ]; then
    log_info "5. Restaurando arquivos estáticos e mídia..."
    cd /home/antuneszi/projeto-mediata
    tar -xzf "${BACKUP_DIR}/${BACKUP_NAME}_files.tar.gz" || \
        log_warn "Falha ao restaurar arquivos (talvez estejam vázios)"
    log_success "Arquivos restaurados"
fi

# 8. Reiniciar aplicação completa
log_info "6. Iniciando aplicação..."
docker-compose -f docker-compose.prod.yml up -d

# 9. Executar migrations
log_info "7. Executando migrations..."
sleep 5
docker-compose -f docker-compose.prod.yml exec -T mediataapp \
    python manage.py migrate --noinput || \
    log_warn "Migrations falharam"

# 10. Coletar static files
log_info "8. Coletando arquivos estáticos..."
docker-compose -f docker-compose.prod.yml exec -T mediataapp \
    python manage.py collectstatic --noinput --clear || \
    log_warn "Collectstatic falhou"

# 11. Verificar saúde
log_info "9. Verificando saúde do sistema..."
sleep 5
for i in {1..10}; do
    if curl -f http://localhost:8000/health/ > /dev/null 2>&1; then
        log_success "Sistema restaurado e funcionando!"
        break
    fi
    if [ $i -eq 10 ]; then
        log_error "Sistema não está respondendo após restauração"
    fi
    sleep 2
done

log_success "========================================="
log_success "Restauração concluída com sucesso!"
log_success "Verifique os dados antes de usar"
log_success "========================================="
