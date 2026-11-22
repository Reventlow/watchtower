"""
Django base settings for Watchtower (Vagt) project.

These settings are shared across all environments.
Environment-specific settings should go in development.py or production.py.

For more information on this file, see:
https://docs.djangoproject.com/en/5.0/topics/settings/
"""

from pathlib import Path

from decouple import Csv, config

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

# Build paths inside the project like this: BASE_DIR / 'subdir'
# BASE_DIR points to the project root (where manage.py is located)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# =============================================================================
# CORE DJANGO SETTINGS
# =============================================================================

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("DJANGO_SECRET_KEY", default="insecure-development-key-change-me")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)

# Hosts/domain names that are valid for this site
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="", cast=Csv())

# Application definition
DJANGO_APPS = [
    # django.contrib.admin, with an admin site that refuses Microsoft (SSO)
    # sessions: apps/accounts/admin_site.py
    "apps.accounts.admin_config.VagtAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_htmx",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.microsoft",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.core",
    "apps.vagt",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# =============================================================================
# MIDDLEWARE
# =============================================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Serve static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",  # i18n support
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",  # HTMX support
    "allauth.account.middleware.AccountMiddleware",
]


# =============================================================================
# URL CONFIGURATION
# =============================================================================

ROOT_URLCONF = "config.urls"


# =============================================================================
# TEMPLATE CONFIGURATION
# =============================================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.version_info",
                "apps.core.context_processors.admin_access",
            ],
        },
    },
]


# =============================================================================
# WSGI/ASGI CONFIGURATION
# =============================================================================

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

# Default to SQLite with WAL mode for better concurrency
# Override with DATABASE_URL for PostgreSQL in production
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            # WAL mode provides better concurrency for SQLite
            "init_command": "PRAGMA journal_mode=WAL;",
        },
    }
}

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =============================================================================
# PASSWORD VALIDATION
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# =============================================================================
# INTERNATIONALIZATION (i18n)
# =============================================================================

# Danish as primary language
LANGUAGE_CODE = "da"

# Copenhagen timezone
TIME_ZONE = "Europe/Copenhagen"

# Enable internationalization
USE_I18N = True

# Enable timezone-aware datetimes
USE_TZ = True

# Supported languages
LANGUAGES = [
    ("da", "Dansk"),
    ("en", "English"),
]

# Path to locale files
LOCALE_PATHS = [
    BASE_DIR / "locale",
]


# =============================================================================
# STATIC FILES (CSS, JavaScript, Images)
# =============================================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# WhiteNoise static file storage with compression
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# =============================================================================
# MEDIA FILES (User uploads)
# =============================================================================

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# =============================================================================
# DJANGO REST FRAMEWORK
# =============================================================================

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.PersonalAccessTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}


# =============================================================================
# AUTHENTICATION
# =============================================================================

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "vagt:board"
LOGOUT_REDIRECT_URL = "login"

# How long a login lasts (default two weeks). A working day (e.g. 12) means
# a user disabled in Entra loses access by the next day.
SESSION_COOKIE_AGE = config("VAGT_SESSION_MAX_HOURS", default=336, cast=int) * 3600


# =============================================================================
# MICROSOFT (ENTRA) SIGN-IN
# =============================================================================
#
# The same set-up as Harbinger and Chronicle: sign-in goes through
# Microsoft, so MFA, Conditional Access and a disabled Entra account apply
# to Vagt too. apps/accounts/adapters.py decides who gets in,
# apps/accounts/backends.py refuses passwords under SSO_ONLY. Off unless
# VAGT_SSO_ENABLED=1.
#
#   VAGT_SSO_ENABLED            "1": the login page is Microsoft only
#   VAGT_SSO_TENANT_ID          the tenant GUID (never "common")
#   VAGT_SSO_CLIENT_ID          the app registration's client id
#   VAGT_SSO_CLIENT_SECRET      its client secret (env file, never compose)
#   VAGT_SSO_REQUIRED_GROUPS    Entra group object ids, comma-separated; the
#                               account must be in one (checked with Graph
#                               at every login)
#   VAGT_SSO_ALLOWED_DOMAINS    default fynbus.dk
#   VAGT_SSO_ALLOW_GUESTS       "1" admits #EXT# guest accounts (default no)
#   VAGT_SSO_AUTO_CREATE_USERS  "1" creates a user for a newcomer (default no:
#                               a superuser creates users in Admin first)
#   VAGT_SSO_ONLY               "1" refuses passwords at /admin/login/ too,
#                               except for ...
#   VAGT_SSO_BREAK_GLASS_USERS  usernames that may still use a password, at
#                               /admin/login/ (local admin accounts)

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.PasswordBackend",
    "apps.accounts.backends.AllauthPasswordBackend",
]

# Nobody signs themselves up; a superuser creates users in Admin.
ACCOUNT_ADAPTER = "apps.accounts.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.SocialAccountAdapter"
# allauth never matches a Microsoft login to a user by e-mail on its own; the
# adapter makes that link once, under its own rules.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
# Addresses from Entra are set by our own admins: no confirmation mail.
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"

_csv = Csv(post_process=lambda values: [v for v in values if v])

SSO_ENABLED = config("VAGT_SSO_ENABLED", default=False, cast=bool)
SSO_TENANT_ID = config("VAGT_SSO_TENANT_ID", default="").strip()
SSO_CLIENT_ID = config("VAGT_SSO_CLIENT_ID", default="").strip()
SSO_CLIENT_SECRET = config("VAGT_SSO_CLIENT_SECRET", default="").strip()
SSO_REQUIRED_GROUPS = [g.lower() for g in config("VAGT_SSO_REQUIRED_GROUPS", default="", cast=_csv)]
SSO_ALLOWED_EMAIL_DOMAINS = [d.lower() for d in config("VAGT_SSO_ALLOWED_DOMAINS", default="fynbus.dk", cast=_csv)]
SSO_ALLOW_GUESTS = config("VAGT_SSO_ALLOW_GUESTS", default=False, cast=bool)
SSO_AUTO_CREATE_USERS = config("VAGT_SSO_AUTO_CREATE_USERS", default=False, cast=bool)
SSO_ONLY = config("VAGT_SSO_ONLY", default=False, cast=bool)
SSO_BREAK_GLASS_USERS = config("VAGT_SSO_BREAK_GLASS_USERS", default="", cast=_csv)

if SSO_ONLY and not SSO_ENABLED:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("VAGT_SSO_ONLY=1 needs VAGT_SSO_ENABLED=1, or nobody could log in.")

if SSO_ENABLED:
    import re as _re

    from django.core.exceptions import ImproperlyConfigured

    _GUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    if not SSO_CLIENT_ID or not SSO_CLIENT_SECRET:
        raise ImproperlyConfigured("VAGT_SSO_ENABLED needs VAGT_SSO_CLIENT_ID and _CLIENT_SECRET.")
    # "common" or "organizations" would let any Microsoft account, from any
    # organisation, authenticate.
    if not _re.fullmatch(_GUID, SSO_TENANT_ID.lower()):
        raise ImproperlyConfigured(
            "VAGT_SSO_ENABLED needs VAGT_SSO_TENANT_ID set to the tenant GUID "
            "(not 'common', 'organizations' or a domain)."
        )
    if len(SSO_REQUIRED_GROUPS) > 20 or not all(_re.fullmatch(_GUID, g) for g in SSO_REQUIRED_GROUPS):
        raise ImproperlyConfigured(
            "VAGT_SSO_REQUIRED_GROUPS must be up to 20 Entra group object ids (GUIDs), comma-separated."
        )
    SOCIALACCOUNT_PROVIDERS = {
        "microsoft": {
            "APP": {"client_id": SSO_CLIENT_ID, "secret": SSO_CLIENT_SECRET},
            "TENANT": SSO_TENANT_ID,
            "SCOPE": ["openid", "email", "profile", "User.Read"],
        }
    }


# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": config("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
