#!/bin/bash

DOMAIN="mediatanordeste.com.br"
EMAIL="mediata.nordeste@gmail.com"  # ⚠️ SUBSTITUA pelo seu email

echo "🚀 Iniciando configuração SSL para $DOMAIN"

# Criar diretórios necessários
mkdir -p certbot/conf certbot/www

# Parar serviços existentes
docker-compose -f docker-compose.prod.yml down

# Iniciar nginx temporariamente (sem SSL ainda)
echo "⏳ Iniciando Nginx temporário..."
docker-compose -f docker-compose.prod.yml up -d nginx

echo "⏳ Aguardando Nginx..."
sleep 10

# Obter certificado SSL
echo "📝 Obtendo certificado Let's Encrypt..."
docker-compose -f docker-compose.prod.yml run --rm certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    -d $DOMAIN \
    -d www.$DOMAIN

if [ $? -eq 0 ]; then
    echo "✅ Certificado SSL obtido com sucesso!"
    
    # Parar todos os serviços
    docker-compose -f docker-compose.prod.yml down
    
    # Iniciar todos os serviços com SSL
    echo "🔄 Iniciando todos os serviços com SSL..."
    docker-compose -f docker-compose.prod.yml up -d
    
    echo ""
    echo "🎉 SSL CONFIGURADO COM SUCESSO!"
    echo "🌐 Acesse: https://$DOMAIN"
    echo "🔧 Se encontrar problemas, verifique os logs:"
    echo "   docker-compose -f docker-compose.prod.yml logs nginx"
else
    echo "❌ Falha ao obter certificado SSL"
    echo "🔍 Verifique se:"
    echo "   - O domínio está apontando para este IP: 34.39.234.74"
    echo "   - As portas 80 e 443 estão abertas no firewall"
    exit 1
fi