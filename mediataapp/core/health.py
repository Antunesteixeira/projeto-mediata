"""
Health Check Endpoint - Django
Adicione ao seu urls.py:
    path('health/', health_check, name='health'),
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import logging

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def health_check(request):
    """
    Endpoint de health check para Docker/Load Balancer.
    Retorna 200 se tudo está ok, 500 se há problemas.
    """
    health_status = {
        'status': 'healthy',
        'checks': {}
    }
    
    # 1. Verificar se Django está respondendo
    health_status['checks']['django'] = 'ok'
    
    # 2. Verificar conexão com banco de dados
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['checks']['database'] = 'ok'
    except Exception as e:
        health_status['checks']['database'] = f'error: {str(e)}'
        health_status['status'] = 'unhealthy'
        logger.error(f"Database health check failed: {e}")
    
    # 3. Verificar se pode escrever em /data/web/media
    try:
        import os
        media_path = '/data/web/media'
        if os.access(media_path, os.W_OK):
            health_status['checks']['media_storage'] = 'ok'
        else:
            health_status['checks']['media_storage'] = 'permission_denied'
            health_status['status'] = 'unhealthy'
    except Exception as e:
        health_status['checks']['media_storage'] = f'error: {str(e)}'
        health_status['status'] = 'unhealthy'
        logger.error(f"Media storage health check failed: {e}")
    
    # 4. Verificar se pode escrever em /data/web/static
    try:
        static_path = '/data/web/static'
        if os.access(static_path, os.W_OK):
            health_status['checks']['static_storage'] = 'ok'
        else:
            health_status['checks']['static_storage'] = 'permission_denied'
            health_status['status'] = 'unhealthy'
    except Exception as e:
        health_status['checks']['static_storage'] = f'error: {str(e)}'
        health_status['status'] = 'unhealthy'
        logger.error(f"Static storage health check failed: {e}")
    
    # Retornar com status HTTP apropriado
    status_code = 200 if health_status['status'] == 'healthy' else 500
    
    return JsonResponse(health_status, status=status_code)
