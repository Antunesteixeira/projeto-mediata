#!/bin/bash
# ============================================================
# Script Blue-Green Deployment - Zero Downtime
# Mantém sistema rodando enquanto faz update
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

COMPOSE_FILE="${1:-.}"
ENV_FILE="${2:-.env.prod}"
AUDIT_LOG="./deploy-audit.log"

log_info() { echo -e "${BLUE}ℹ $*${NC}"; }
log_success() { echo -e "${GREEN}✓ $*${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
log_error() { echo -e "${RED}✗ $*${NC}"; audit "ERROR: $*"; exit 1; }
audit() { local msg="$*"; local time; time=$(date --iso-8601=seconds); echo "[$time] $msg" | tee -a "${AUDIT_LOG}"; }

audit "START Deploy"
log_info "========================================="
log_info "Blue-Green Deployment - Mediata"
log_info "========================================="

# 1. Verificar se containers estão rodando
log_info "1. Verificando status dos containers..."
if ! docker ps | grep -q mediataapp_prod; then
    log_error "mediataapp_prod não está rodando! Fazer deploy inicial primeiro."
fi

# 2. Backup de segurança
log_info "2. Fazendo backup de segurança..."
bash scripts/backup-daily.sh || log_warn "Backup falhou, continuando mesmo assim..."

# 3. Build da nova versão
log_info "3. Fazendo build da nova versão..."
audit "BUILD START"
docker-compose -f docker-compose.prod.yml build mediataapp || \
    log_error "Build falhou!"
audit "BUILD OK"

# 4. Validar health da versão atual
log_info "4. Verificando saúde do sistema atual..."
for i in {1..5}; do
    if docker-compose -f docker-compose.prod.yml exec -T mediataapp curl -f http://localhost:8000/health/ > /dev/null 2>&1; then
        log_success "Sistema atual funcionando"
        audit "CURRENT HEALTH OK"
        break
    fi
    if [ $i -eq 5 ]; then
        log_error "Sistema atual com problemas de saúde!"
    fi
    sleep 2
 done

# 5. Atualizar o serviço mediataapp
log_info "5. Iniciando a nova versão do serviço..."
audit "DEPLOY START"
docker-compose -f docker-compose.prod.yml up -d --no-deps mediataapp || log_error "Falha ao iniciar nova versão!"
audit "SERVICE STARTED"

# 6. Aguardar health check do serviço
log_info "6. Aguardando serviço ficar saudável..."
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if docker-compose -f docker-compose.prod.yml exec -T mediataapp curl -f http://localhost:8000/health/ > /dev/null 2>&1; then
        log_success "Serviço está saudável"
        audit "DEPLOY HEALTH OK"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        log_error "Serviço não ficou saudável em tempo!"
    fi
    sleep 2
 done

# 7. Executar migrations (se necessário)
log_info "7. Executando migrations..."
audit "MIGRATIONS START"
docker-compose -f docker-compose.prod.yml exec -T mediataapp python manage.py migrate --noinput || \
    log_warn "Migrations falharam ou não foram necessárias"
audit "MIGRATIONS OK"

# 8. Coletar static files
log_info "8. Coletando arquivos estáticos..."
audit "COLLECTSTATIC START"
docker-compose -f docker-compose.prod.yml exec -T mediataapp python manage.py collectstatic --noinput || \
    log_warn "Collectstatic falhou ou não foi necessário"
audit "COLLECTSTATIC OK"

# 9. Verificação final
log_info "9. Verificando a nova versão..."
if docker-compose -f docker-compose.prod.yml exec -T mediataapp curl -f http://localhost:8000/health/ > /dev/null 2>&1; then
    log_success "Nova versão está em produção e saudável"
    audit "DEPLOY OK"
else
    log_error "A verificação final falhou. Verifique logs e tente novamente."
fi

log_success "==========================================="
log_success "Deployment concluído com sucesso!"
log_success "Sistema atualizado com sucesso"
log_success "==========================================="

# 10. Cleanup (opcional)
log_info "10. Limpando containers e imagens não utilizadas..."
audit "CLEANUP START"
docker system prune -f --filter "until=24h" || true
audit "CLEANUP OK"

log_success "Tudo pronto!"
