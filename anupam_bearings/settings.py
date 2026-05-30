from pathlib import Path
import os
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-anupam-bearings-dev-key-change-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'products',
    'contact',
    'chatbot',
    'dashboard',
    'django_celery_beat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'anupam_bearings.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'anupam_bearings.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE', default='django.db.backends.sqlite3'),
        'NAME': config('DB_NAME', default=str(BASE_DIR / 'db.sqlite3')),
        'USER': config('DB_USER', default=''),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default=''),
        'PORT': config('DB_PORT', default=''),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

RESEND_API_KEY = config('RESEND_API_KEY', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@anupambearings.com')
COMPANY_EMAIL = config('COMPANY_EMAIL', default='info@anupambearings.com')

OLLAMA_URL = config('OLLAMA_URL', default='http://localhost:11434/api/generate')
OLLAMA_MODEL = config('OLLAMA_MODEL', default='llama3')

# ─────────────────────────────────────────────
# CELERY CONFIGURATION
# ─────────────────────────────────────────────
REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

CELERY_BROKER_URL         = REDIS_URL
CELERY_RESULT_BACKEND     = REDIS_URL
CELERY_ACCEPT_CONTENT     = ['json']
CELERY_TASK_SERIALIZER    = 'json'
CELERY_RESULT_SERIALIZER  = 'json'
CELERY_TIMEZONE           = 'Asia/Kolkata'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT    = 120        # hard kill after 2 min
CELERY_TASK_SOFT_TIME_LIMIT = 90       # SoftTimeLimitExceeded at 90s
CELERY_WORKER_CONCURRENCY = 4          # 4 parallel workers
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # one task at a time per worker slot

# ─────────────────────────────────────────────
# REDIS CACHE (for RAG query caching)
# ─────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',          # ← django-redis backend
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',  # ← now valid
        },
        'TIMEOUT': 3600,
    }
}

# ─────────────────────────────────────────────
# RAG CONFIGURATION
# ─────────────────────────────────────────────
RAG_INDEX_DIR       = config('RAG_INDEX_DIR',       default=str(BASE_DIR / 'data' / 'faiss_index'))
RAG_KNOWLEDGE_DIR   = config('RAG_KNOWLEDGE_DIR',   default=str(BASE_DIR / 'data' / 'knowledge_base'))
RAG_TOP_K           = config('RAG_TOP_K',           default=5,    cast=int)
RAG_SCORE_THRESHOLD = config('RAG_SCORE_THRESHOLD', default=0.22, cast=float)
EMBEDDING_MODEL     = config('EMBEDDING_MODEL',     default='all-MiniLM-L6-v2')

# LLM concurrency and timeouts
OLLAMA_MAX_CONCURRENT = config('OLLAMA_MAX_CONCURRENT', default=4,  cast=int)
OLLAMA_TIMEOUT        = config('OLLAMA_TIMEOUT',        default=120, cast=int)
OLLAMA_MAX_RETRIES    = config('OLLAMA_MAX_RETRIES',    default=2,  cast=int)

# ─────────────────────────────────────────────
# RATE LIMITING
# ─────────────────────────────────────────────
RATELIMIT_USE_CACHE = 'default'
RATELIMIT_ENABLE    = True

# ─────────────────────────────────────────────
# SECURITY HARDENING
# ─────────────────────────────────────────────
SECURE_BROWSER_XSS_FILTER   = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS             = 'DENY'

# ─────────────────────────────────────────────
# PAGINATION
# ─────────────────────────────────────────────
DASHBOARD_PAGE_SIZE = 20
PUBLIC_PRODUCTS_PAGE_SIZE = 12

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class':     'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django':  {'handlers': ['console'], 'level': 'WARNING'},
        'rag':     {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'chatbot': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}

# ─────────────────────────────────────────────
# LLM BACKEND SELECTION
# ─────────────────────────────────────────────
# Options: 'groq' (fast, free) | 'ollama' (local, slow on CPU)
LLM_BACKEND   = config('LLM_BACKEND',   default='groq')
LLM_TIMEOUT   = config('LLM_TIMEOUT',   default=30, cast=int)
LLM_MAX_RETRIES = config('LLM_MAX_RETRIES', default=2, cast=int)

# Groq (get free key at console.groq.com)
GROQ_API_KEY  = config('GROQ_API_KEY',  default='')
GROQ_MODEL    = config('GROQ_MODEL',    default='llama3-8b-8192')
