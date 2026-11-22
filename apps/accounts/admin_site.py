"""Django admin that refuses Microsoft (SSO) sessions.

Installed through :class:`apps.accounts.apps.VagtAdminConfig` in place of
``django.contrib.admin``, so ``admin.site`` (and every ``@admin.register``)
is this site. Django's own rule (active staff user) still applies; on top
of it a session started by Microsoft sign-in has no access. Such a user
sees Django's "you are not authorised" login page, where only a local
account (under VAGT_SSO_ONLY: a break-glass account) can sign in.
"""

from django.contrib import admin

from .access import is_sso_session


class VagtAdminSite(admin.AdminSite):
    site_header = "Vagt administration"
    site_title = "Vagt admin"

    def has_permission(self, request) -> bool:
        return super().has_permission(request) and not is_sso_session(request)
