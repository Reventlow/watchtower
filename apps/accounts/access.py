"""Admin access: Microsoft (SSO) sessions never reach the admin pages.

Vagt's admin pages are Django admin (/admin/) and the superuser-only pages
in the app (Dokumentation). They are for administrators who signed in with
a *local* account; a session that came from Microsoft sign-in is refused
there, even when its user is a superuser. Board, log, controllers and the
profile page are unaffected.

How a session is told apart: every login first clears the mark (Django's
``user_logged_in``), and a Microsoft login then sets it (allauth's
``user_logged_in``, which carries ``sociallogin`` and is sent right after
Django's). A password login (Django admin login; Vagt's page only without SSO)
therefore always yields an unmarked session, and an SSO login a marked one.
"""

from __future__ import annotations

SSO_SESSION_KEY = "vagt_sso_login"


def clear_sso_mark(sender, request=None, user=None, **kwargs) -> None:
    """Django's user_logged_in: every login starts unmarked."""
    if request is not None and hasattr(request, "session"):
        request.session.pop(SSO_SESSION_KEY, None)


def mark_sso_login(sender, request=None, user=None, sociallogin=None, **kwargs) -> None:
    """allauth's user_logged_in: mark the session when it came from SSO."""
    if sociallogin is not None and request is not None and hasattr(request, "session"):
        request.session[SSO_SESSION_KEY] = True


def is_sso_session(request) -> bool:
    """True when the current session was started by a Microsoft sign-in."""
    session = getattr(request, "session", None)
    return bool(session is not None and session.get(SSO_SESSION_KEY))


def has_admin_access(request) -> bool:
    """Superusers signed in with a local account; never an SSO session."""
    user = getattr(request, "user", None)
    return bool(user is not None and user.is_active and user.is_superuser and not is_sso_session(request))
