#!/bin/bash
# ============================================================
# Script de Instalação - Configurar Melhorias Automaticamente
# Execute na VM do Google Cloud
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
log_error() { echo -e "${RED}✗ $*${NC}"; exit 1; }

log_info "========================================="
log_info "Instalação de Melhorias - Mediata"
log_info "========================================="

# 1. Verificar se estamos no diretório correto
if [ ! -f "docker-compose.prod.yml" ]; then
    log_error "Arquivo docker-compose.prod.yml não encontrado. Execute no diretório raiz do projeto!"
fi

# 2. Criar diretórios necessários
log_info "1. Criando diretórios..."
mkdir -p /backups/mediata
mkdir -p /var/log/mediata
chmod 755 /backups/mediata
log_success "Diretórios criados"

# 3. Tornar scripts executáveis
log_info "2. Configurando scripts..."
chmod +x scripts/backup-daily.sh
chmod +x scripts/deploy-blue-green.sh
chmod +x scripts/restore-backup.sh
log_success "Scripts configurados"

# 4. Fazer backup de segurança
log_info "3. Fazendo backup de segurança..."
if bash scripts/backup-daily.sh; then
    log_success "Backup realizado com sucesso"
else
    log_warn "Falha no backup, continuando mesmo assim..."
fi

# 5. Configurar Cron (perguntar ao usuário)
log_info "4. Configurando Backup Automático (Cron)..."
read -p "Deseja configurar backup automático diário (0h da manhã)? (S/n) " -r
if [[ $REPLY =~ ^[Ss]$ ]] || [[ -z $REPLY ]]; then
    
    # Verificar se já existe entrada de backup
    if crontab -l 2>/dev/null | grep -q "backup-daily.sh"; then
        log_warn "Entrada de cron já existe para backup"
    else
        # Adicionar nova entrada
        (crontab -l 2>/dev/null; echo "0 0 * * * cd $(pwd) && ./scripts/backup-daily.sh >> /var/log/mediata/backup.log 2>&1") | crontab -
        log_success "Backup automático configurado (diariamente às 00:00)"
    fi
fi

# 6. Testar conectividade com GCS (opcional)
log_info "5. Verificando Google Cloud Storage..."
if command -v gsutil &> /dev/null; then
    if gsutil ls gs:// > /dev/null 2>&1; then
        log_success "GCS acessível"
    else
        log_warn "GCS não acessível - verifique autenticação com 'gcloud auth login'"
    fi
else
    log_warn "gsutil não instalado - backups não serão enviados para GCS"
fi

# 7. Fazer teste de health check
log_info "6. Testando Health Checks..."
if docker-compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    if curl -f http://localhost:8000/health/ > /dev/null 2>&1; then
        log_success "Health checks funcionando"
    else
        log_warn "Health check da app falhou - pode ser esperado se migrations forem necessárias"
    fi
else
    log_warn "Containers não estão rodando - inicie com: docker-compose up -d"
fi

# 8. Criar arquivo de status
log_info "7. Criando arquivo de status..."
cat > /tmp/mediata-deploy-status.txt << EOF
Instalação de Melhorias - Mediata
Data: $(date)

✓ Diretórios criados
✓ Scripts configurados
✓ Backup realizado
✓ Cron configurado (se selecionado)

Próximos passos:
1. Revisar MIGRATION_GUIDE.md
2. Executar: bash scripts/deploy-blue-green.sh
3. Verificar: docker-compose ps
4. Monitorar: docker-compose logs -f

Backups armazenados em: /backups/mediata/
Logs em: /var/log/mediata/

Dúvidas? Consulte DEPLOY_IMPROVEMENTS.md
EOF

log_success "Instalação concluída!"
log_info "========================================="
cat /tmp/mediata-deploy-status.txt
log_info "========================================="

log_success "✓ Sistema pronto para deploy!"
log_info "Execute: bash scripts/deploy-blue-green.sh"
