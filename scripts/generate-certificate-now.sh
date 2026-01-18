#!/bin/bash
set -e

DOMAIN="mediatanordeste.com.br"
EMAIL="mediata.nordeste@gmail.com"

echo "🔧 GERAÇÃO DE CERTIFICADO SSL"
echo "=============================="

# 1. VERIFICAÇÃO DNS
echo ""
echo "1️⃣  VERIFICAÇÃO DNS (OBRIGATÓRIA)"
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s http://ipinfo.io/ip)
DOMAIN_IP=$(dig +short $DOMAIN 2>/dev/null | head -1)

echo "   Este servidor: $SERVER_IP"
echo "   $DOMAIN aponta para: ${DOMAIN_IP:-NÃO RESOLVE}"

if [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
    echo ""
    echo "⚠️  ⚠️  ⚠️  ALERTA: DNS NÃO CONFIGURADO ⚠️  ⚠️  ⚠️"
    echo "O certificado NÃO será emitido se o DNS não estiver correto!"
    echo ""
    echo "CONFIGURE NO SEU REGISTRADOR:"
    echo "--------------------------------"
    echo "Tipo: A"
    echo "Nome/Host: @"
    echo "Valor: $SERVER_IP"
    echo "TTL: 3600"
    echo ""
    echo "Tipo: CNAME"
    echo "Nome/Host: www"
    echo "Valor: $DOMAIN"
    echo "TTL: 3600"
    echo ""
    echo "Após configurar, aguarde propagação (pode levar horas)"
    echo ""
    read -p "Já configurou e quer tentar mesmo assim? (s/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        echo "Configure o DNS primeiro!"
        exit 1
    fi
fi

# 2. PREPARAR
echo ""
echo "2️⃣  PREPARANDO AMBIENTE"
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true
sudo rm -rf certbot/conf/* certbot/www/*
mkdir -p certbot/{conf,www}
sudo chown -R 1003:1004 certbot/  # Seu UID:GID
sudo chmod -R 755 certbot/

# Matar processos na porta 80
sudo fuser -k 80/tcp 2>/dev/null || true

# 3. GERAR CERTIFICADO
echo ""
echo "3️⃣  GERANDO CERTIFICADO"
echo "   Tentando método STANDALONE..."

# Primeiro teste dry-run
echo "   🧪 Teste dry-run..."
docker run --rm \
  -p 80:80 \
  -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
  certbot/certbot certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  --no-eff-email \
  -d "$DOMAIN" \
  --preferred-challenges http \
  --dry-run 2>&1 | tee /tmp/certbot-dryrun.log

if grep -q "Congratulations" /tmp/certbot-dryrun.log; then
    echo "   ✅ Dry-run bem sucedido!"
    
    # Gerar certificado real
    echo "   🎯 Gerando certificado REAL..."
    docker run --rm \
      -p 80:80 \
      -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
      certbot/certbot certonly \
      --standalone \
      --non-interactive \
      --agree-tos \
      --email "$EMAIL" \
      --no-eff-email \
      -d "$DOMAIN" \
      --preferred-challenges http
    
    if [ $? -eq 0 ]; then
        echo "   ✅✅✅ CERTIFICADO OBTIDO! ✅✅✅"
    fi
else
    echo "   ❌ Dry-run falhou"
    echo "   Verificando erro..."
    grep -i "error\|failed\|invalid" /tmp/certbot-dryrun.log | head -5
fi

# 4. VERIFICAR RESULTADO
echo ""
echo "4️⃣  VERIFICANDO RESULTADO"
if [ -f "certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    echo "   ✅ Certificado encontrado!"
    echo "   📄 Arquivos:"
    ls -la certbot/conf/live/$DOMAIN/
    
    # Corrigir permissões
    sudo chmod 600 certbot/conf/live/$DOMAIN/privkey.pem
    
    # Adicionar www se não tiver
    if [ ! -f "certbot/conf/live/$DOMAIN-0001/fullchain.pem" ]; then
        echo ""
        echo "   ➕ Adicionando www.$DOMAIN..."
        docker run --rm \
          -p 80:80 \
          -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
          certbot/certbot certonly \
          --standalone \
          --non-interactive \
          --agree-tos \
          --email "$EMAIL" \
          --no-eff-email \
          -d "$DOMAIN" \
          -d "www.$DOMAIN" \
          --preferred-challenges http \
          --expand 2>&1 | grep -i "success\|congrat"
    fi
    
    # 5. INICIAR SERVIÇOS
    echo ""
    echo "5️⃣  INICIANDO SERVIÇOS"
    docker-compose -f docker-compose.prod.yml up -d
    
    echo ""
    echo "📊 Status:"
    docker-compose -f docker-compose.prod.yml ps
    
    echo ""
    echo "🎉🎉🎉 CONCLUÍDO! 🎉🎉🎉"
    echo "🌐 Acesse: https://$DOMAIN"
    echo "⚠️  Pode levar alguns minutos para funcionar"
    
else
    echo "   ❌❌❌ FALHA ❌❌❌"
    echo "   O certificado NÃO foi gerado."
    echo ""
    echo "🔍 SOLUÇÃO:"
    echo "1. Configure o DNS corretamente"
    echo "2. Verifique firewall da Google Cloud"
    echo "   gcloud compute firewall-rules create allow-http --allow tcp:80"
    echo "3. Aguarde propagação DNS"
    exit 1
fi
