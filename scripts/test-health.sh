#!/bin/bash
# ============================================================
# Script de Teste Rápido - Validar Deploy
# Execute após fazer deploy para verificar se tudo está ok
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ $*${NC}"; }
log_success() { echo -e "${GREEN}✓ $*${NC}"; }
log_fail() { echo -e "${RED}✗ $*${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $*${NC}"; }

PASS=0
FAIL=0
WARN=0

check_test() {
    local name="$1"
    local result="$2"
    
    if [ "$result" == "0" ]; then
        log_success "$name"
        ((PASS++))
    else
        log_fail "$name"
        ((FAIL++))
    fi
}

log_info "========================================="
log_info "Teste Rápido de Saúde - Mediata"
log_info "========================================="

# 1. Verificar se containers estão rodando
log_info "1. Verificando containers..."
docker-compose ps | grep -q "mediataapp_prod" && result=0 || result=1
check_test "Container mediataapp_prod" $result

docker-compose ps | grep -q "psql_prod" && result=0 || result=1
check_test "Container psql_prod" $result

docker-compose ps | grep -q "nginx_prod" && result=0 || result=1
check_test "Container nginx_prod" $result

# 2. Verificar health dos containers
log_info "2. Verificando health checks..."
sleep 2  # Dar tempo para health checks

HEALTH=$(docker-compose ps mediataapp_prod --format "{{.Status}}" 2>/dev/null || echo "Down")
if echo "$HEALTH" | grep -q "healthy"; then
    log_success "mediataapp health status: healthy"
    ((PASS++))
elif echo "$HEALTH" | grep -q "Up"; then
    log_warn "mediataapp health status: starting"
    ((WARN++))
else
    log_fail "mediataapp não está rodando"
    ((FAIL++))
fi

# 3. Verificar resposta HTTP
log_info "3. Testando endpoints HTTP..."
if curl -f http://localhost:8000/health/ > /dev/null 2>&1; then
    log_success "Django health endpoint"
    ((PASS++))
else
    log_warn "Django health endpoint (pode estar iniciando)"
    ((WARN++))
fi

if curl -f http://localhost/ > /dev/null 2>&1; then
    log_success "Nginx / (homepage)"
    ((PASS++))
else
    log_fail "Nginx / (homepage)"
    ((FAIL++))
fi

# 4. Verificar banco de dados
log_info "4. Testando banco de dados..."
if docker-compose exec -T psql pg_isready -U ${POSTGRES_USER:-postgres} > /dev/null 2>&1; then
    log_success "PostgreSQL respondendo"
    ((PASS++))
else
    log_fail "PostgreSQL não respondendo"
    ((FAIL++))
fi

# 5. Verificar permissões de arquivos
log_info "5. Verificando permissões..."
if [ -w "data/web/static" ] && [ -w "data/web/media" ]; then
    log_success "Permissões de escrita em data/web/"
    ((PASS++))
else
    log_warn "Permissões de escrita em data/web/ (pode ser esperado)"
    ((WARN++))
fi

# 6. Verificar logs por erros críticos
log_info "6. Procurando por erros críticos nos logs..."
ERROR_COUNT=$(docker-compose logs 2>/dev/null | grep -i "error\|exception\|critical" | wc -l || echo "0")
if [ "$ERROR_COUNT" -lt 5 ]; then
    log_success "Sem erros críticos detectados"
    ((PASS++))
else
    log_warn "Detectados $ERROR_COUNT erros nos logs (pode ser esperado)"
    ((WARN++))
fi

# 7. Verificar espaço em disco
log_info "7. Verificando espaço em disco..."
DISK_USAGE=$(df -h . | awk 'NR==2 {print $(NF-1)}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 90 ]; then
    log_success "Espaço em disco: ${DISK_USAGE}% utilizado"
    ((PASS++))
else
    log_fail "Espaço em disco crítico: ${DISK_USAGE}%"
    ((FAIL++))
fi

# 8. Verificar backup
log_info "8. Verificando backup..."
BACKUP_COUNT=$(find /backups/mediata -type f -name "*_db.sql.gz" 2>/dev/null | wc -l || echo "0")
if [ "$BACKUP_COUNT" -gt 0 ]; then
    LATEST_BACKUP=$(ls -t /backups/mediata/*_db.sql.gz 2>/dev/null | head -1)
    BACKUP_TIME=$(stat -c %y "$LATEST_BACKUP" 2>/dev/null | cut -d' ' -f1)
    log_success "Backup disponível: $BACKUP_TIME"
    ((PASS++))
else
    log_warn "Nenhum backup encontrado"
    ((WARN++))
fi

# 9. Verificar conexão ao GCS (se configurado)
log_info "9. Verificando backup em GCS..."
if command -v gsutil &> /dev/null && [ -n "$GCS_BACKUP_BUCKET" ]; then
    if gsutil ls "$GCS_BACKUP_BUCKET" > /dev/null 2>&1; then
        log_success "Google Cloud Storage acessível"
        ((PASS++))
    else
        log_warn "GCS não acessível (verifique gcloud auth)"
        ((WARN++))
    fi
else
    log_warn "gsutil não disponível ou GCS_BACKUP_BUCKET não configurado"
    ((WARN++))
fi

# 10. Verificar SSL (se em HTTPS)
log_info "10. Verificando SSL/TLS..."
if [ -d "certbot/conf/live" ]; then
    CERT_COUNT=$(ls certbot/conf/live/ 2>/dev/null | wc -l)
    if [ "$CERT_COUNT" -gt 0 ]; then
        log_success "Certificados SSL encontrados"
        ((PASS++))
    else
        log_warn "Nenhum certificado SSL encontrado"
        ((WARN++))
    fi
else
    log_warn "Diretório de certificados não encontrado"
    ((WARN++))
fi

# Resumo
log_info "========================================="
echo ""
log_success "PASSOU: $PASS"
log_warn "AVISOS: $WARN"
if [ $FAIL -gt 0 ]; then
    log_fail "FALHOU: $FAIL"
fi
echo ""

if [ $FAIL -eq 0 ]; then
    log_success "✓ Todos os testes passaram!"
    log_info "Sistema está saudável e pronto para uso."
    exit 0
else
    log_warn "⚠ Alguns testes falharam, verifique acima."
    log_info "Dica: rode 'docker-compose logs' para ver mais detalhes"
    exit 1
fi
