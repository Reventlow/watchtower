"""Sign-in for Vagt: local accounts plus Microsoft (Entra) SSO."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"

    def ready(self):
        from allauth.account.signals import user_logged_in as allauth_logged_in
        from django.contrib.auth.signals import user_logged_in as django_logged_in

        from . import checks  # noqa: F401  (registers the system checks)
        from .access import clear_sso_mark, mark_sso_login

        # Django's signal fires inside login(), before allauth's: clear, then mark.
        django_logged_in.connect(clear_sso_mark, dispatch_uid="vagt_clear_sso_mark")
        allauth_logged_in.connect(mark_sso_login, dispatch_uid="vagt_mark_sso_login")

