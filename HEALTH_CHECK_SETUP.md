# Como Adicionar Health Check ao Django

## Passo 1: Adicionar import ao urls.py

No arquivo `mediataapp/mediata/urls.py` (ou seu arquivo principal de URLs), adicione:

```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.health import health_check  # ← ADICIONE ESTA LINHA

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('usuarios.urls')),
    path('clientes/', include('clientes.urls')),
    path('colaboradores/', include('colaborador.urls')),
    path('insumos/', include('insumos.urls')),
    path('tickets/', include('tickets.urls')),
    
    # ← ADICIONE ESTA LINHA
    path('health/', health_check, name='health'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

## Passo 2: Testar o endpoint

```bash
# Local (em desenvolvimento)
python manage.py runserver
curl http://localhost:8000/health/

# Produção (via Docker)
docker-compose exec mediataapp curl http://localhost:8000/health/

# Esperado:
# {"status": "healthy", "checks": {"django": "ok", "database": "ok", ...}}
```

## Passo 3: Verificar se Docker está usando corretamente

O arquivo `docker-compose.prod.yml` já tem configurado:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health/", "||", "exit", "1"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

Isso significa:
- ✅ Docker verifica a saúde a cada 30 segundos
- ✅ Se 3 tentativas falham, marca como "unhealthy"
- ✅ Aguarda 40 segundos antes de iniciar os testes (para migrations)

## Passo 4: Verificar status de saúde

```bash
# Ver status de todos os containers
docker-compose ps

# Exemplo de saída saudável:
# NAME                COMMAND                 STATUS
# mediataapp_prod     "python manage.py ..."  Up 2 minutes (healthy)
# psql_prod           "docker-entrypoint..."  Up 2 minutes (healthy)
# nginx_prod          "/docker-entrypoint..."  Up 2 minutes (healthy)

# Ver status detalhado de um container
docker inspect --format='{{.State.Health.Status}}' mediataapp_prod

# Ver histórico de health checks
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{"\n"}}{{end}}' mediataapp_prod
```

## Customizações Possíveis

Se quiser adicionar mais verificações ao health check, edite `mediataapp/core/health.py`:

```python
# Exemplo: Adicionar verificação de Redis
try:
    import redis
    r = redis.Redis(host='redis', port=6379, db=0, socket_connect_timeout=2)
    r.ping()
    health_status['checks']['redis'] = 'ok'
except Exception as e:
    health_status['checks']['redis'] = f'error: {str(e)}'
    health_status['status'] = 'unhealthy'
```

## Dúvidas?

Consulte:
- [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md) - Guia completo de migração
- [DEPLOY_IMPROVEMENTS.md](./DEPLOY_IMPROVEMENTS.md) - Resumo das melhorias
