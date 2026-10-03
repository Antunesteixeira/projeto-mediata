"""Configuração compartilhada para desenvolvimento com Docker."""
from .settings import *  # noqa: F403

MEDIA_URL = '/media/'
MEDIA_ROOT = '/data/web/media'
CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000']
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
