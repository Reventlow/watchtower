"""
Django production settings for Watchtower (Vagt) project.

These settings extend base.py with production-hardened configuration.
Security settings are strictly enforced.

Usage:
    export DJANGO_SETTINGS_MODULE=config.settings.production
    gunicorn config.wsgi:application

IMPORTANT: Ensure all environment variables are properly set before deployment.
"""

from decouple import config

from .base import *  # noqa: F401, F403

# =============================================================================
# DEBUG CONFIGURATION
# =============================================================================

# CRITICAL: Never enable DEBUG in production
DEBUG = False


# =============================================================================
# HOST CONFIGURATION
# =============================================================================

# ALLOWED_HOSTS must be explicitly set in production
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", cast=lambda v: [s.strip() for s in v.split(",")])

# Validate that ALLOWED_HOSTS is not empty
if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
    raise ValueError("DJANGO_ALLOWED_HOSTS must be set in production")


# =============================================================================
# SECRET KEY VALIDATION
# =============================================================================

# Ensure a proper secret key is set
SECRET_KEY = config("DJANGO_SECRET_KEY")

if "insecure" in SECRET_KEY.lower() or "change-me" in SECRET_KEY.lower():
    raise ValueError("DJANGO_SECRET_KEY must be set to a secure value in production")


# =============================================================================
# SECURITY SETTINGS
# =============================================================================

# HTTPS Settings
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("DJANGO_SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS (HTTP Strict Transport Security)
# Start with a short max-age and increase once confirmed working
SECURE_HSTS_SECONDS = config("DJANGO_SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Content Security
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

# CSRF Settings
CSRF_TRUSTED_ORIGINS = config(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default="",
    cast=lambda v: [s.strip() for s in v.split(",") if s.strip()],
)


# =============================================================================
# DATABASE (Production)
# =============================================================================

# Use SQLite in /data directory for Docker volume persistence
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/data/db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL;",
        },
    }
}


# =============================================================================
# CACHING (Production)
# =============================================================================

# Configure Redis or Memcached for production
# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.redis.RedisCache",
#         "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
#     }
# }


# =============================================================================
# EMAIL (Production)
# =============================================================================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@example.com")


# =============================================================================
# LOGGING (Production - less verbose, file-based)
# =============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "json": {
            "()": "django.utils.log.ServerFormatter",
            "format": "[{server_time}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


# =============================================================================
# PERFORMANCE
# =============================================================================

# Database connection pooling (if using PostgreSQL with psycopg)
# DATABASES["default"]["OPTIONS"] = {
#     "pool": True,
# }

# Template caching is automatic when DEBUG=False
