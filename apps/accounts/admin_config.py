"""django.contrib.admin, installed with Vagt's admin site.

Listed in INSTALLED_APPS in place of "django.contrib.admin". A module of
its own: next to AccountsConfig, Django would see two default AppConfigs.
"""

from django.contrib.admin.apps import AdminConfig


class VagtAdminConfig(AdminConfig):
    """django.contrib.admin with Vagt's admin site (no SSO sessions)."""

    default_site = "apps.accounts.admin_site.VagtAdminSite"
