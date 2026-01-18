#!/bin/bash

DOMAIN="mediatanordeste.com.br"
EMAIL="mediata.nordeste@gmail.com"  # ⚠️ SUBSTITUA pelo seu email
SERVER_IP="34.39.252.54"  # ✅ IP CORRIGIDO

echo "🚀 Iniciando configuração SSL para $DOMAIN"
echo "📡 IP do servidor: $SERVER_IP"

# Verificar se está sendo executado como root/sudo
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  Recomendado executar com sudo para garantir permissões adequadas"
    echo "   sudo $0"
    read -p "Continuar mesmo assim? (s/N): " -n 1 -r
    echo
    [[ ! $REPLY =~ ^[Ss]$ ]] && exit 1
fi

# 1. Verificar e configurar permissões das pastas
echo "📁 Configurando permissões das pastas..."
mkdir -p certbot/conf certbot/www certbot/logs

# Definir permissões apropriadas
chmod 755 certbot
chmod 755 certbot/www
chmod 755 certbot/logs
chmod 755 certbot/conf

# 2. Verificar se as pastas do projeto existem
if [ ! -f "docker-compose.prod.yml" ]; then
    echo "❌ docker-compose.prod.yml não encontrado!"
    exit 1
fi

# 3. Verificar configuração do DNS
echo "🔍 Verificando configuração do DNS..."
echo "   Domínio: $DOMAIN"
echo "   Resolução DNS atual:"

# Obter IPs do domínio
DOMAIN_IPS=$(dig +short $DOMAIN | tr '\n' ',' | sed 's/,$//')
echo "   IPs encontrados: $DOMAIN_IPS"

if echo "$DOMAIN_IPS" | grep -q "$SERVER_IP"; then
    echo "✅ DNS configurado corretamente! $DOMAIN aponta para $SERVER_IP"
else
    echo "⚠️  ATENÇÃO: $DOMAIN NÃO está apontando para $SERVER_IP"
    echo "   IPs encontrados: $DOMAIN_IPS"
    echo "   IP esperado: $SERVER_IP"
    echo ""
    echo "📌 Para o SSL funcionar, você DEVE configurar:"
    echo "   Registro A: $DOMAIN → $SERVER_IP"
    echo "   Registro A: www.$DOMAIN → $SERVER_IP"
    echo ""
    read -p "Continuar mesmo assim? (pode falhar) (s/N): " -n 1 -r
    echo
    [[ ! $REPLY =~ ^[Ss]$ ]] && exit 1
fi

# 4. Verificar se as portas estão livres
echo "🔌 Verificando portas 80 e 443..."
if ss -tuln | grep ':80 ' > /dev/null; then
    echo "❌ Porta 80 já está em uso por outro processo"
    ss -tuln | grep ':80 '
    read -p "Tentar parar o serviço que usa a porta 80? (s/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        sudo fuser -k 80/tcp
        sleep 2
    else
        exit 1
    fi
fi

if ss -tuln | grep ':443 ' > /dev/null; then
    echo "❌ Porta 443 já está em uso por outro processo"
    ss -tuln | grep ':443 '
    read -p "Tentar parar o serviço que usa a porta 443? (s/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        sudo fuser -k 443/tcp
        sleep 2
    else
        exit 1
    fi
fi

# 5. Parar serviços existentes
echo "⏹️  Parando serviços..."
docker-compose -f docker-compose.prod.yml down

# 6. Configurar nginx temporário para o desafio ACME
echo "🔧 Preparando configuração nginx temporária para o certbot..."

# Criar configuração nginx temporária se não existir
mkdir -p nginx
cat > nginx/temp-certbot.conf << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri =404;
    }
    
    location / {
        return 301 https://\$host\$request_uri;
    }
}
EOF
echo "✅ Configuração nginx temporária criada"

# 7. Iniciar nginx temporariamente
echo "⏳ Iniciando Nginx para validação do certbot..."
docker-compose -f docker-compose.prod.yml up -d nginx

echo "⏳ Aguardando inicialização do Nginx..."
sleep 15

# Verificar se o nginx está rodando
if ! docker-compose -f docker-compose.prod.yml ps nginx | grep -q "Up"; then
    echo "❌ Nginx não iniciou corretamente"
    echo "📋 Logs do nginx:"
    docker-compose -f docker-compose.prod.yml logs nginx --tail=50
    exit 1
fi

# 8. Testar acesso ao webroot
echo "🔍 Testando acesso ao diretório webroot..."
TEST_FILE="test_$(date +%s).txt"
echo "certbot-validation-test" > certbot/www/.well-known/acme-challenge/$TEST_FILE

# Criar estrutura de diretórios se não existir
mkdir -p certbot/www/.well-known/acme-challenge

echo "🧪 Testando acesso HTTP ao domínio..."
HTTP_TEST=$(curl -s -o /dev/null -w "%{http_code}\n" --max-time 10 http://$DOMAIN/.well-known/acme-challenge/$TEST_FILE)

if [ "$HTTP_TEST" = "200" ] || [ "$HTTP_TEST" = "301" ] || [ "$HTTP_TEST" = "302" ]; then
    echo "✅ Webroot acessível via HTTP (código: $HTTP_TEST)"
else
    echo "❌ Não foi possível acessar o diretório webroot via HTTP (código: $HTTP_TEST)"
    echo ""
    echo "🔍 Diagnóstico:"
    echo "   1. Testando conectividade com o domínio:"
    ping -c 3 $DOMAIN
    echo ""
    echo "   2. Verificando se o nginx está ouvindo na porta 80:"
    docker-compose -f docker-compose.prod.yml exec nginx netstat -tuln | grep :80
    echo ""
    echo "   3. Conteúdo do diretório webroot:"
    ls -la certbot/www/.well-known/acme-challenge/
    echo ""
    echo "   4. Teste manual:"
    echo "      curl -v http://$DOMAIN/.well-known/acme-challenge/$TEST_FILE"
    echo ""
    
    # Tentar teste local
    echo "   5. Testando localmente no container:"
    docker-compose -f docker-compose.prod.yml exec nginx curl -s http://localhost/.well-known/acme-challenge/$TEST_FILE
    
    rm certbot/www/.well-known/acme-challenge/$TEST_FILE
    exit 1
fi
rm certbot/www/.well-known/acme-challenge/$TEST_FILE

# 9. Obter certificado SSL
echo ""
echo "📝 Obtendo certificado Let's Encrypt..."
echo "   Domínio: $DOMAIN e www.$DOMAIN"
echo "   Email: $EMAIL"
echo "   IP do servidor: $SERVER_IP"
echo ""

# Primeiro fazer um teste seco (dry-run) para verificar se tudo está ok
echo "🧪 Executando teste seco (dry-run) primeiro..."
docker-compose -f docker-compose.prod.yml run --rm certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    --dry-run \
    -d $DOMAIN \
    -d www.$DOMAIN

DRY_RUN_RESULT=$?

if [ $DRY_RUN_RESULT -eq 0 ]; then
    echo "✅ Teste seco bem-sucedido! Obtendo certificado real..."
    
    # Obter certificado real
    docker-compose -f docker-compose.prod.yml run --rm certbot certonly \
        --webroot \
        --webroot-path /var/www/certbot \
        --email $EMAIL \
        --agree-tos \
        --no-eff-email \
        --non-interactive \
        --verbose \
        -d $DOMAIN \
        -d www.$DOMAIN
    
    CERT_RESULT=$?
else
    echo "❌ Teste seco falhou. Corrija os problemas antes de continuar."
    CERT_RESULT=$DRY_RUN_RESULT
fi

if [ $CERT_RESULT -eq 0 ]; then
    echo "✅ Certificado SSL obtido com sucesso!"
    
    # 10. Verificar se os certificados foram criados
    echo "🔍 Verificando certificados criados..."
    if [ -f "certbot/conf/live/$DOMAIN/fullchain.pem" ] && [ -f "certbot/conf/live/$DOMAIN/privkey.pem" ]; then
        echo "   ✅ Certificados encontrados em certbot/conf/live/$DOMAIN/"
        ls -la "certbot/conf/live/$DOMAIN/"
        
        # Ajustar permissões dos certificados
        chmod 644 certbot/conf/live/$DOMAIN/fullchain.pem
        chmod 600 certbot/conf/live/$DOMAIN/privkey.pem
        
        # Mostrar informações do certificado
        echo ""
        echo "📄 Informações do certificado:"
        openssl x509 -in "certbot/conf/live/$DOMAIN/fullchain.pem" -text -noout | grep -E "Subject:|Not Before:|Not After:|DNS:"
    else
        echo "⚠️  Certificados não encontrados no caminho esperado"
        echo "   Procurando em outros locais..."
        find certbot/conf -name "*.pem" -type f | head -10
    fi
    
    # 11. Parar todos os serviços
    echo "⏹️  Parando serviços temporários..."
    docker-compose -f docker-compose.prod.yml down
    
    # 12. Iniciar todos os serviços com SSL
    echo "🔄 Iniciando todos os serviços com SSL..."
    docker-compose -f docker-compose.prod.yml up -d
    
    # 13. Verificar se os serviços estão rodando
    echo "🔍 Verificando status dos serviços..."
    docker-compose -f docker-compose.prod.yml ps
    
    echo ""
    echo "🎉 SSL CONFIGURADO COM SUCESSO!"
    echo "🌐 Acesse: https://$DOMAIN"
    echo ""
    echo "📋 RESUMO DA CONFIGURAÇÃO:"
    echo "   Domínio: $DOMAIN"
    echo "   IP do servidor: $SERVER_IP"
    echo "   Certificado: certbot/conf/live/$DOMAIN/"
    echo "   Data de expiração: $(openssl x509 -in "certbot/conf/live/$DOMAIN/fullchain.pem" -enddate -noout | cut -d= -f2)"
    echo ""
    echo "🔧 Comandos úteis:"
    echo "   Ver logs do nginx: docker-compose -f docker-compose.prod.yml logs nginx"
    echo "   Ver status dos serviços: docker-compose -f docker-compose.prod.yml ps"
    echo "   Renew certificados: docker-compose -f docker-compose.prod.yml run --rm certbot renew"
    echo "   Testar renew: docker-compose -f docker-compose.prod.yml run --rm certbot renew --dry-run"
    
    # Testar acesso HTTPS
    echo ""
    echo "🧪 Testando conexão HTTPS..."
    sleep 10  # Aguardar nginx iniciar completamente
    
    HTTPS_TEST=$(curl -s -o /dev/null -w "%{http_code}\n" --max-time 10 https://$DOMAIN)
    
    if [ "$HTTPS_TEST" = "200" ] || [ "$HTTPS_TEST" = "301" ] || [ "$HTTPS_TEST" = "302" ]; then
        echo "✅ HTTPS funcionando corretamente! (código: $HTTPS_TEST)"
        
        # Testar SSL com openssl
        echo ""
        echo "🔐 Testando qualidade do SSL..."
        echo "   Verificação do certificado:"
        openssl s_client -connect $DOMAIN:443 -servername $DOMAIN < /dev/null 2>/dev/null | grep -E "Verify|SSL-Session"
        
    else
        echo "⚠️  HTTPS retornou código $HTTPS_TEST"
        echo "   Isso pode ser normal se o site redirecionar ou exigir autenticação"
    fi
    
    # Verificar SSL Labs grade (informação)
    echo ""
    echo "📊 Para verificar a qualidade do SSL, acesse:"
    echo "   https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
    
else
    echo "❌ Falha ao obter certificado SSL (código: $CERT_RESULT)"
    echo ""
    echo "🔍 Solução de problemas detalhada:"
    echo ""
    echo "   1. ✅ VERIFICAÇÃO DE DNS:"
    echo "      Domínio: $DOMAIN"
    echo "      IP atual: $DOMAIN_IPS"
    echo "      IP esperado: $SERVER_IP"
    echo ""
    echo "   2. ✅ VERIFICAÇÃO DE PORTAS:"
    echo "      Porta 80: $(ss -tuln | grep ':80 ' && echo 'OCUPADA' || echo 'LIVRE')"
    echo "      Porta 443: $(ss -tuln | grep ':443 ' && echo 'OCUPADA' || echo 'LIVRE')"
    echo ""
    echo "   3. ✅ VERIFICAÇÃO DO NGINX:"
    docker-compose -f docker-compose.prod.yml ps nginx
    echo ""
    echo "   4. 🔧 TESTES MANUAIS RECOMENDADOS:"
    echo "      a. Testar acesso webroot:"
    echo "         curl -v http://$DOMAIN/.well-known/acme-challenge/test"
    echo ""
    echo "      b. Verificar logs do certbot:"
    echo "         docker-compose -f docker-compose.prod.yml logs --tail=100"
    echo ""
    echo "      c. Testar desafio ACME manualmente:"
    echo "         mkdir -p certbot/www/.well-known/acme-challenge"
    echo "         echo 'test-content' > certbot/www/.well-known/acme-challenge/test.txt"
    echo "         curl http://$DOMAIN/.well-known/acme-challenge/test.txt"
    echo ""
    echo "   5. 📞 SE NADA FUNCIONAR:"
    echo "      - Verifique se há firewall bloqueando: sudo ufw status"
    echo "      - Verifique se o provedor de hospedagem permite portas 80/443"
    echo "      - Aguarde propagação do DNS (pode levar até 24h)"
    
    # Limpar serviços
    docker-compose -f docker-compose.prod.yml down
    exit 1
fi

echo ""
echo "✅ Script concluído em: $(date)"
