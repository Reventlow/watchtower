"""
Django development settings for Watchtower (Vagt) project.

These settings extend base.py with development-specific configuration.
DEBUG is enabled and additional development tools are configured.

Usage:
    export DJANGO_SETTINGS_MODULE=config.settings.development
    python manage.py runserver
"""

from .base import *  # noqa: F401, F403

# =============================================================================
# DEBUG CONFIGURATION
# =============================================================================

DEBUG = True

# Allow all hosts in development
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]


# =============================================================================
# INSTALLED APPS (Development extras)
# =============================================================================

# Django Debug Toolbar - disabled (uncomment to enable)
# try:
#     import debug_toolbar  # noqa: F401
#
#     INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
#     MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
# except ImportError:
#     pass


# =============================================================================
# DEBUG TOOLBAR CONFIGURATION (if enabled above)
# =============================================================================

INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]


# =============================================================================
# EMAIL CONFIGURATION (Console backend for development)
# =============================================================================

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# =============================================================================
# STATIC FILES (Development - no compression)
# =============================================================================

# Use simple storage in development for faster reloads
STORAGES = {  # noqa: F405
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


# =============================================================================
# REST FRAMEWORK (Development)
# =============================================================================

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",  # Enable browsable API
]


# =============================================================================
# LOGGING (More verbose in development)
# =============================================================================

LOGGING["loggers"]["django"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405
