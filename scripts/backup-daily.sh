#!/bin/bash
# ============================================================
# Script de Backup Diário - PostgreSQL + Arquivos
# Mantém backups locais + envia para Google Cloud Storage
# ============================================================

set -e  # Parar em erro

# Configurações
BACKUP_DIR="/backups/mediata"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="mediata_backup_${TIMESTAMP}"
DB_CONTAINER="psql_prod"
PROJECT_ID="${GCP_PROJECT_ID}"  # Definir em .env
BUCKET_NAME="${GCS_BACKUP_BUCKET}"  # Ex: gs://mediata-backups

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}[BACKUP] Iniciando backup em ${TIMESTAMP}${NC}"

# 1. Criar diretório de backup
mkdir -p "${BACKUP_DIR}"

# 2. Backup do PostgreSQL
echo -e "${YELLOW}[BACKUP] Fazendo dump do PostgreSQL...${NC}"
docker exec "${DB_CONTAINER}" pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
    | gzip > "${BACKUP_DIR}/${BACKUP_NAME}_db.sql.gz"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Backup do banco de dados concluído${NC}"
    ls -lh "${BACKUP_DIR}/${BACKUP_NAME}_db.sql.gz"
else
    echo -e "${RED}✗ ERRO no backup do banco de dados${NC}"
    exit 1
fi

# 3. Backup dos arquivos (static + media)
echo -e "${YELLOW}[BACKUP] Compactando arquivos estáticos e mídia...${NC}"
cd /home/antuneszi/projeto-mediata
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}_files.tar.gz" \
    data/web/static data/web/media 2>/dev/null || true

if [ -f "${BACKUP_DIR}/${BACKUP_NAME}_files.tar.gz" ]; then
    echo -e "${GREEN}✓ Backup de arquivos concluído${NC}"
    ls -lh "${BACKUP_DIR}/${BACKUP_NAME}_files.tar.gz"
fi

# 4. Enviar para Google Cloud Storage (se configurado)
if [ -n "${BUCKET_NAME}" ] && [ -n "${PROJECT_ID}" ]; then
    echo -e "${YELLOW}[BACKUP] Enviando para Google Cloud Storage...${NC}"
    
    if command -v gsutil &> /dev/null; then
        gsutil -m cp "${BACKUP_DIR}/${BACKUP_NAME}"* "${BUCKET_NAME}/" 2>&1 | tail -5
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Upload para GCS concluído${NC}"
        else
            echo -e "${RED}⚠ Falha no upload, mas backup local preservado${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ gsutil não encontrado, pulando GCS${NC}"
    fi
fi

# 5. Limpeza de backups antigos (manter últimos 7 dias)
echo -e "${YELLOW}[BACKUP] Limpando backups antigos (> 7 dias)...${NC}"
find "${BACKUP_DIR}" -type f -mtime +7 -delete

echo -e "${GREEN}[BACKUP] ✓ Backup concluído com sucesso!${NC}"
echo -e "${GREEN}[BACKUP] Próximo backup: $(date -d '+24 hours' '+%Y-%m-%d %H:%M:%S')${NC}"
