"""The login page: "Log ind med Microsoft", or a password form without SSO."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect


class LoginView(auth_views.LoginView):
    """Django's login view; Microsoft only while SSO is on.

    With VAGT_SSO_ENABLED the page offers only Microsoft sign-in, and a
    posted username and password is refused without being checked. The one
    password login left is Django admin's own (/admin/login/), for local
    administrator accounts: a Microsoft session never reaches the admin
    pages (apps/accounts/access.py). Without SSO the page is the plain
    password form, as before.
    """

    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if settings.SSO_ENABLED:
            messages.error(request, "Log ind med din FynBus Microsoft-konto.")
            return redirect("login")
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context["sso_enabled"] = settings.SSO_ENABLED
        context["show_password_form"] = not settings.SSO_ENABLED
        return context
