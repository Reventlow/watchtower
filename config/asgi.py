"""
ASGI config for Watchtower (Vagt) project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see:
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/

Usage with Uvicorn:
    uvicorn config.asgi:application --host 0.0.0.0 --port 8000

Usage with Daphne:
    daphne config.asgi:application -b 0.0.0.0 -p 8000

Note: ASGI is required for Django Channels (WebSocket support).
For standard HTTP-only deployments, WSGI (wsgi.py) is recommended.
"""

import os

from django.core.asgi import get_asgi_application

# Default to production settings in ASGI context
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
