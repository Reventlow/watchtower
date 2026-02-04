"""
Django settings package for Watchtower (Vagt).

Settings are split into:
- base.py: Common settings shared across all environments
- development.py: Development-specific settings (DEBUG=True)
- production.py: Production-hardened settings

Usage:
    Set DJANGO_SETTINGS_MODULE environment variable to select the configuration:
    - config.settings.development (default)
    - config.settings.production
"""
