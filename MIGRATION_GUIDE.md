# 🚀 Guia de Migração Segura - Melhorias de Deploy
## Sistema sem Perda de Dados

---

## 📋 Pré-requisitos

Antes de começar:
1. ✅ Sistema Mediata rodando em produção
2. ✅ Acesso SSH à VM do Google Cloud
3. ✅ Backup recente dos dados
4. ✅ Tempo livre (15-30 minutos recomendado)
5. ✅ Conhecimento básico de Docker/Linux

---

## ⚠️ PASSO 0: Fazer Backup Completo (CRÍTICO!)

```bash
# SSH na sua VM
ssh seu-usuario@seu-ip-vm

# Entrar no diretório do projeto
cd /home/antuneszi/projeto-mediata

# Fazer backup manual
./scripts/backup-daily.sh

# Verificar se backup foi criado
ls -lh /backups/mediata/
```

**Saída esperada:**
```
-rw-r--r-- 1 user group 250M Jan 15 14:30 mediata_backup_20240115_143022_db.sql.gz
-rw-r--r-- 1 user group 120M Jan 15 14:30 mediata_backup_20240115_143022_files.tar.gz
```

---

## 📝 PASSO 1: Atualizar Arquivos de Configuração

### 1.1 Clonar/Baixar os Novos Arquivos

Você recebeu 3 arquivos novos:
- `docker-compose.prod.yml` (versão melhorada)
- `scripts/backup-daily.sh`
- `scripts/deploy-blue-green.sh`
- `scripts/restore-backup.sh`
- `dotenv_files/.env.prod.example`

**Na VM do Google:**

```bash
# Fazer backup do arquivo antigo
cp docker-compose.prod.yml docker-compose.prod.yml.backup

# Substituir pela versão nova (você fará isso manualmente)
# Copie e cole o conteúdo do novo docker-compose.prod.yml
# OU use um editor como nano/vim
```

### 1.2 Rendibilizar Scripts

```bash
chmod +x scripts/backup-daily.sh
chmod +x scripts/deploy-blue-green.sh
chmod +x scripts/restore-backup.sh

# Verificar se estão executáveis
ls -l scripts/*.sh
```

---

## 🔧 PASSO 2: Atualizar .env de Produção

```bash
# Fazer backup da configuração atual
cp ./dotenv_files/.env.prod ./dotenv_files/.env.prod.backup

# Revisar as variáveis importantes (NÃO mude se estiver funcionando!)
# Apenas adicione as novas variáveis de logging/backup

# Exemplo de novas linhas a adicionar:
cat >> ./dotenv_files/.env.prod << 'EOF'

# ========== NOVOS PARA BACKUP ==========
GCP_PROJECT_ID=seu-gcp-project-id
GCS_BACKUP_BUCKET=gs://mediata-backups
BACKUP_RETENTION_DAYS=7
BACKUP_SCHEDULE=daily

# ========== NOVOS PARA LOGS ==========
LOG_LEVEL=INFO
SENTRY_DSN=https://seu-sentry-key@sentry.io/1234567
EOF
```

---

## ✅ PASSO 3: Testar Novos Arquivos (Sem Fazer Downtime)

```bash
# Primeiro, verificar status atual
docker-compose -f docker-compose.prod.yml ps

# Saída esperada:
# NAME                  STATUS
# nginx_prod            Up ...
# mediataapp_prod       Up ...
# psql_prod             Up ...
# certbot_prod          Up ...

# Fazer dry-run do deployment (sem fazer nada)
docker-compose -f docker-compose.prod.yml config > /dev/null && \
    echo "✓ Sintaxe do Docker Compose está correcta"

# Teste de health check (verificar se os serviços estão respondendo)
curl -I http://localhost/  # Deve retornar 200
curl -I http://localhost:8000/health/  # Deve retornar 200
```

---

## 🔄 PASSO 4: Implementar Novas Configurações (COM DOWNTIME MÍNIMO)

### Opção A: Deployment Seguro com Blue-Green (RECOMENDADO)

```bash
# Este script faz tudo automaticamente:
# 1. Faz backup
# 2. Build nova imagem
# 3. Inicia novos containers
# 4. Testa saúde
# 5. Faz switch gradual (sem downtime total)

bash scripts/deploy-blue-green.sh

# Ver progresso em outro terminal:
watch -n 1 'docker-compose ps'
```

### Opção B: Atualização Controlada (Se Blue-Green falhar)

```bash
# 1. Fazer backup
bash scripts/backup-daily.sh

# 2. Parar apenas a aplicação (banco de dados continua)
docker-compose -f docker-compose.prod.yml down

# 3. Fazer pull da nova versão
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml build --no-cache

# 4. Iniciar tudo de novo
docker-compose -f docker-compose.prod.yml up -d

# 5. Executar migrations (se houver mudanças no BD)
docker-compose -f docker-compose.prod.yml exec mediataapp \
    python manage.py migrate --noinput

# 6. Coletar static files
docker-compose -f docker-compose.prod.yml exec mediataapp \
    python manage.py collectstatic --noinput --clear
```

**Tempo estimado de downtime: 2-5 minutos**

---

## ✨ PASSO 5: Verificar se Tudo Funciona

```bash
# Ver logs dos containers
docker-compose -f docker-compose.prod.yml logs -f

# Testar acesso à aplicação
curl -v http://localhost/
curl -v https://seu-dominio.com/

# Verificar saúde dos serviços
docker-compose -f docker-compose.prod.yml ps

# Conectar ao banco de dados para verificar dados
docker-compose -f docker-compose.prod.yml exec psql \
    psql -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT COUNT(*) FROM clientes_cliente;"

# Esperado: número de clientes > 0
```

---

## 📅 PASSO 6: Configurar Backup Automático

```bash
# Adicionar tarefa cron para backup diário (midnight)
crontab -e

# Adicionar esta linha:
0 0 * * * /home/antuneszi/projeto-mediata/scripts/backup-daily.sh >> /var/log/mediata-backup.log 2>&1

# Verificar se foi adicionado:
crontab -l | grep backup-daily
```

---

## 🚨 PASSO 7: Plano de Recuperação (Em Caso de Emergência)

Se algo der errado:

### Opção 1: Rollback Rápido
```bash
# Voltar para a versão anterior
docker-compose -f docker-compose.prod.yml.backup down
cp docker-compose.prod.yml docker-compose.prod.yml.novo
cp docker-compose.prod.yml.backup docker-compose.prod.yml

docker-compose -f docker-compose.prod.yml up -d
```

### Opção 2: Restaurar do Backup
```bash
# Se perdeu dados (ÚLLTIMA OPÇÃO)
bash scripts/restore-backup.sh mediata_backup_20240115_143022

# Se backup está no GCS:
bash scripts/restore-backup.sh mediata_backup_20240115_143022 --from-gcs
```

---

## 📊 Monitoramento Contínuo

Após a migração, monitore:

```bash
# Ver uso de recursos
docker stats

# Ver logs de erros
docker-compose logs --tail=100 | grep -i error

# Verificar backups sendo criados
ls -lh /backups/mediata/ | tail -5

# Alertas de certificado SSL (renova automaticamente agora)
docker-compose logs certbot | tail -20
```

---

## ✅ Checklist Final

- [ ] Backup feito e verificado
- [ ] Arquivos atualizados
- [ ] Docker-compose sintaxe correcta
- [ ] Deployment executado com sucesso
- [ ] Health checks passando
- [ ] Dados ainda existem (SELECT * FROM clientes_cliente)
- [ ] Aplicação acessível via browser
- [ ] Backup cron configurado
- [ ] Logs monitorados
- [ ] Documentação atualizada

---

## 🆘 Troubleshooting

### Problema: Container não inicia
```bash
# Ver logs de erro
docker-compose logs mediataapp

# Mais detalhes
docker logs mediataapp_prod --tail=50
```

### Problema: Banco de dados não conecta
```bash
# Verificar se PostgreSQL está rodando
docker ps | grep psql

# Testar conexão
docker-compose exec psql pg_isready -U $POSTGRES_USER
```

### Problema: SSL/HTTPS não funciona
```bash
# Verificar certificado
docker-compose exec nginx ls -l /etc/letsencrypt/live/

# Ver logs do certbot
docker-compose logs certbot
```

---

## 📞 Suporte

Em caso de dúvidas:
1. Consulte esta guia novamente
2. Verifique os logs: `docker-compose logs`
3. Faça rollback se necessário
4. Contacte o desenvolvedor

**Lembre-se:** Seus dados estão protegidos pelos backups! ✅
