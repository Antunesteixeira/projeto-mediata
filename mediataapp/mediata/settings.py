"""
Django settings for mediata project.
"""

from pathlib import Path
import os
from datetime import timedelta
from django.contrib.messages import constants as messages

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR.parent / 'data' / 'web'

# Security settings
SECRET_KEY = os.getenv('SECRET_KEY')  # ❗DEVE ser definida via environment
DEBUG = bool(int(os.getenv('DEBUG', '0')))

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv('ALLOWED_HOSTS', '').split(',')
    if h.strip()
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # apps do sistema
    'core',
    'usuarios',
    'tickets',
    'insumos',
    'clientes',
    'colaborador',
    'relatorios',
    # apps de terceiros
    'rolepermissions',
    'widget_tweaks',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_auto_logout.middleware.auto_logout',
]

ROOT_URLCONF = 'mediata.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['templates/'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django_auto_logout.context_processors.auto_logout_client',
            ],
        },
    },
]

WSGI_APPLICATION = 'mediata.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME': os.getenv('POSTGRES_DB', 'db_mediata'),
        'USER': os.getenv('POSTGRES_USER', 'mediata_user'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'mediata_password'),
        'HOST': os.getenv('POSTGRES_HOST', 'psql'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

if DEBUG:
    # Modo desenvolvimento
    STATICFILES_DIRS = [
        DATA_DIR / 'static',  # ou DATA_DIR / 'static' dependendo da sua estrutura
    ]
    STATIC_URL = '/static/'
else:
    # Modo produção
    STATIC_URL = '/static/'
    STATIC_ROOT = DATA_DIR / 'static'  # collectstatic vai coletar aqui
    
    MEDIA_URL = '/media/'
    MEDIA_ROOT = DATA_DIR / 'media'  # uploads de usuários
    
# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = '/dashboard/'
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

MESSAGE_TAGS = {
    messages.ERROR: 'danger',
}

ROLEPERMISSIONS_MODULE = 'usuarios.roles'
handler404 = 'core.erro_404'

# Configurações de sessão e auto-logout
SESSION_SAVE_EVERY_REQUEST = True
AUTO_LOGOUT = {
    'IDLE_TIME': timedelta(minutes=20),
    'SESSION_TIME': timedelta(minutes=60),
    'MESSAGE': 'A sessão expirou. Faça login novamente para continuar.',
    'REDIRECT_TO_LOGIN_IMMEDIATELY': True,
}

# ✅ Configurações CSRF e CORS dinâmicas
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
]

CSRF_COOKIE_DOMAIN = os.getenv('CSRF_COOKIE_DOMAIN', None)

# ✅ Configurações de segurança para produção
if not DEBUG:
    #SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')