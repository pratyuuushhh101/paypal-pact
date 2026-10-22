"""Django settings for pact_core project.

Configured with python-decouple for strict separation of secrets and environment variables.
"""

from datetime import timedelta
from pathlib import Path
from typing import Any
from decouple import Csv, config

BASE_DIR: Path = Path(__file__).resolve().parent.parent

# Security Settings
SECRET_KEY: str = config("DJANGO_SECRET_KEY")
DEBUG: bool = config("DJANGO_DEBUG", default=False, cast=bool)
# ALLOWED_HOSTS: list[str] = config(
#     "DJANGO_ALLOWED_HOSTS",
#     default="127.0.0.1,localhost",
#     cast=Csv(),
# )
ALLOWED_HOSTS = ['*']
# Application definition
DJANGO_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS: list[str] = [
    "rest_framework",
    "corsheaders",
    "rest_framework_simplejwt",
]

LOCAL_APPS: list[str] = [
    "apps.users.apps.UsersConfig",
    "escrow.apps.EscrowConfig",
]

INSTALLED_APPS: list[str] = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Custom User Model
AUTH_USER_MODEL: str = "users.PactUser"

MIDDLEWARE: list[str] = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# CORS Configuration
CORS_ALLOWED_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ALLOW_CREDENTIALS: bool = True


ROOT_URLCONF: str = "pact_core.urls"

TEMPLATES: list[dict[str, Any]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION: str = "pact_core.wsgi.application"
ASGI_APPLICATION: str = "pact_core.asgi.application"

# Database Configuration (PostgreSQL)
DATABASES: dict[str, dict[str, Any]] = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="pact_core_db"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default="postgres"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default=5432, cast=int),
    }
}

# Cache Configuration (Used by PayPal token caching and rate limiting)
CACHES: dict[str, dict[str, Any]] = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "pact-core-cache",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE: str = "en-us"
TIME_ZONE: str = "UTC"
USE_I18N: bool = True
USE_TZ: bool = True

# Static files
STATIC_URL: str = "static/"
STATIC_ROOT: Path = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD: str = "django.db.models.BigAutoField"

# Django REST Framework
REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT: dict[str, Any] = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Celery Broker & Backend
CELERY_BROKER_URL: str = config("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND: str = config("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/0")
CELERY_ACCEPT_CONTENT: list[str] = ["json"]
CELERY_TASK_SERIALIZER: str = "json"
CELERY_RESULT_SERIALIZER: str = "json"
CELERY_TIMEZONE: str = TIME_ZONE

# PayPal Configuration
PAYPAL_CLIENT_ID: str = config("PAYPAL_CLIENT_ID", default="")
PAYPAL_CLIENT_SECRET: str = config("PAYPAL_CLIENT_SECRET", default="")
PAYPAL_ENVIRONMENT: str = config("PAYPAL_ENVIRONMENT", default="sandbox")
PAYPAL_WEBHOOK_ID: str = config("PAYPAL_WEBHOOK_ID", default="")

# External Integrations
EXTERNAL_API_KEY: str = config("EXTERNAL_API_KEY", default="")

# Groq API Configuration
GROQ_API_KEY: str = config("GROQ_API_KEY", default="")
GROQ_MODEL: str = config("GROQ_MODEL", default="llama3-70b-8192")
GROQ_TIMEOUT: int = config("GROQ_TIMEOUT", default=30, cast=int)

# Email Configuration
EMAIL_BACKEND: str = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL: str = config("DEFAULT_FROM_EMAIL", default="notifications@pact-escrow.com")


