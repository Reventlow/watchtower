"""
WSGI config for Watchtower (Vagt) project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see:
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/

Usage with Gunicorn:
    gunicorn config.wsgi:application --bind 0.0.0.0:8000

Usage with uWSGI:
    uwsgi --module config.wsgi:application --http :8000
"""

import os

from django.core.wsgi import get_wsgi_application

# Default to production settings in WSGI context
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()
