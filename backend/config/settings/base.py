import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-me-in-production')

DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_extensions',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'saa_collector',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'saa_collector.middlewares.request_logging.RequestLoggingMiddleware',
    'saa_collector.middlewares.dev_token.DevTokenMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'mysql.connector.django',
        'NAME': os.getenv('DATABASE_NAME', 'saa'),
        'USER': os.getenv('DATABASE_USER', 'root'),
        'PASSWORD': os.getenv('DATABASE_PASSWORD', ''),
        'HOST': os.getenv('DATABASE_HOST', 'localhost'),
        'PORT': os.getenv('DATABASE_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'saa_collector.authentications.DevTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://localhost:3000',
]

DEV_MODE_TOKEN = os.getenv('DEV_MODE_TOKEN', None)

UC_API = os.getenv('UC_API', '')
UC_KEY = os.getenv('UC_KEY', '')
UC_APPID = os.getenv('UC_APPID', '')
UC_ADMIN_USERS = [u.strip() for u in os.getenv('UC_ADMIN_USERS', '').split(',') if u.strip()]

# 数据源配置: 'akshare' 或 'tushare'
DATA_SOURCE = os.getenv('DATA_SOURCE', 'tushare')


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_optional_int(name, default=None):
    value = os.getenv(name)
    if value is None or value == '':
        return default
    return int(value)

COLLECTOR_CELERY_QUEUE = os.getenv('COLLECTOR_CELERY_QUEUE', 'collector')
COLLECTOR_EXECUTION_QUEUE = os.getenv('COLLECTOR_EXECUTION_QUEUE', 'collector')
COLLECTOR_SCHEDULER_QUEUE = os.getenv('COLLECTOR_SCHEDULER_QUEUE', 'scheduler')

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_TASK_DEFAULT_QUEUE = COLLECTOR_CELERY_QUEUE
CELERY_TASK_ROUTES = {
    'saa_collector.execute_collect_plan': {'queue': COLLECTOR_EXECUTION_QUEUE},
    'saa_collector.scan_due_collect_schedules': {'queue': COLLECTOR_SCHEDULER_QUEUE},
}
CELERY_TASK_ACKS_LATE = env_bool('CELERY_TASK_ACKS_LATE', False)
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.getenv('CELERY_WORKER_PREFETCH_MULTIPLIER', '1'))
CELERY_TASK_TIME_LIMIT = env_optional_int('CELERY_TASK_TIME_LIMIT')
CELERY_TASK_SOFT_TIME_LIMIT = env_optional_int('CELERY_TASK_SOFT_TIME_LIMIT')
CELERY_BEAT_SCHEDULE = {
    'scan-due-collect-schedules': {
        'task': 'saa_collector.scan_due_collect_schedules',
        'schedule': float(os.getenv('COLLECTOR_SCHEDULE_SCAN_SECONDS', '60')),
        'options': {'queue': COLLECTOR_SCHEDULER_QUEUE},
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {collect_context}{message}',
            'style': '{',
        },
        'simple': {
            'format': '{asctime} - {levelname} - {collect_context}{message}',
            'style': '{',
        },
    },
    'filters': {
        'collect_execution_context': {
            '()': 'saa_collector.logging_filters.CollectExecutionContextFilter',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'filters': ['collect_execution_context'],
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'saa_collector': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
