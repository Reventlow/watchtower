"""django-allauth adapters: who may sign in to Vagt, and how.

Nobody signs themselves up:

* **Local accounts** are created by a superuser in Django Admin. allauth's
  own sign-up page is mounted with the package but leads to the login page
  (config/urls.py), and :class:`AccountAdapter` closes it as well.

* **Microsoft SSO** (when ``SSO_ENABLED``) is the other way in, and
  :class:`SocialAccountAdapter` decides who passes, as in Harbinger and
  Chronicle:

  - The login authority is pinned to one tenant (``VAGT_SSO_TENANT_ID``
    must be a tenant GUID, see settings), so only accounts in that
    directory can authenticate at all.
  - Guest accounts (``#EXT#`` in the UPN) are refused unless
    ``SSO_ALLOW_GUESTS`` is on.
  - The account's address must be in ``SSO_ALLOWED_EMAIL_DOMAINS``.
  - With ``SSO_REQUIRED_GROUPS`` set, the account must be in one of those
    Entra groups. Vagt asks Graph at every login (``POST
    /me/checkMemberGroups``, which needs only the ``User.Read`` permission
    the login already has), and refuses when Graph says no or cannot
    answer.
  - The Microsoft account is tied to a Vagt user by its Entra object id
    (allauth's uid for this provider). On the *first* SSO login of an
    existing user, the link is made once by e-mail address. That is safe
    only because the tenant is pinned and addresses in it are set by our
    own admins (the "nOAuth" attack relies on a foreign tenant choosing any
    address). After that the object id alone decides.
  - An account with no Vagt user is refused, unless
    ``SSO_AUTO_CREATE_USERS`` is on; then a plain (non-staff) user is
    created for it. Every Vagt user can change controller statuses, so
    leave auto-creation off unless ``SSO_REQUIRED_GROUPS`` limits who can
    reach this point.

Who may sign in with Microsoft at all is decided in Entra first: the
enterprise app has "Assignment required" on, with only the assigned group
allowed. ``SSO_REQUIRED_GROUPS`` repeats that rule inside Vagt, so a stray
direct assignment or a mis-set switch in Entra is not enough.
"""

from __future__ import annotations

import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

GRAPH_CHECK_MEMBER_GROUPS = "https://graph.microsoft.com/v1.0/me/checkMemberGroups"


class AccountAdapter(DefaultAccountAdapter):
    """Local accounts: self sign-up is closed; superusers create accounts."""

    def is_open_for_signup(self, request) -> bool:
        return False

    def add_message(self, request, level, message_template=None, message_context=None,
                    extra_tags="", message=None):
        """Only errors. Vagt's pages show no messages except errors on the
        login page, so allauth's "logged in as ..." would linger in the
        messages cookie and appear on the next login page, after logout,
        on a shared PC too."""
        if level >= messages.ERROR:
            super().add_message(request, level, message_template, message_context,
                                extra_tags=extra_tags, message=message)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Microsoft SSO: only accounts in our tenant, linked by Entra object id."""

    def pre_social_login(self, request, sociallogin) -> None:
        """Refuse foreign accounts; link an existing user on first login."""
        data = sociallogin.account.extra_data or {}
        upn = (data.get("userPrincipalName") or "").lower()
        email = (data.get("mail") or data.get("userPrincipalName") or "").strip().lower()

        if "#ext#" in upn and not settings.SSO_ALLOW_GUESTS:
            self._refuse(request, sociallogin, "guest account",
                         "Gæstekonti kan ikke logge ind i Vagt.")
        if not _domain_allowed(email):
            self._refuse(request, sociallogin, f"address outside allowed domains: {email!r}",
                         "Din Microsoft-konto hører ikke til en tilladt organisation.")

        if settings.SSO_REQUIRED_GROUPS:
            member = self._in_required_group(sociallogin)
            if member is None:
                self._refuse(request, sociallogin, "group membership could not be checked",
                             "Vagt kunne ikke tjekke din adgang hos Microsoft. Prøv igen om lidt.")
            if not member:
                self._refuse(request, sociallogin, f"not in SSO_REQUIRED_GROUPS: {upn!r}",
                             "Din Microsoft-konto har ikke adgang til Vagt. Kontakt IT, hvis du skal bruge den.")

        if sociallogin.is_existing:
            return  # already tied to a user by its object id

        # First SSO login: tie it to the existing user with that address,
        # if there is exactly one active one.
        User = get_user_model()
        matches = list(User.objects.filter(email__iexact=email, is_active=True)[:2])
        if len(matches) == 1:
            sociallogin.connect(request, matches[0])
            logger.info("SSO: linked Microsoft account %s to existing user %s",
                        sociallogin.account.uid, matches[0].get_username())
        elif len(matches) > 1:
            self._refuse(request, sociallogin, f"{len(matches)} users share {email!r}",
                         "Flere brugere har samme e-mailadresse. Kontakt IT.")
        elif not settings.SSO_AUTO_CREATE_USERS:
            self._refuse(request, sociallogin, f"no Vagt user with {email!r}",
                         "Der findes ingen Vagt-bruger til din Microsoft-konto. Bed IT om at oprette en.")

    def is_open_for_signup(self, request, sociallogin) -> bool:
        """A new user from SSO only when auto-creation is switched on."""
        return bool(settings.SSO_AUTO_CREATE_USERS)

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        logger.info("SSO: created user %s for Microsoft account %s",
                    user.get_username(), sociallogin.account.uid)
        return user

    def _in_required_group(self, sociallogin) -> bool | None:
        """Is the signed-in account in one of SSO_REQUIRED_GROUPS?

        checkMemberGroups answers with the subset of the given ids the user
        belongs to (transitively). None means Graph could not be asked or
        gave no usable answer; the caller refuses then too (fail closed).
        """
        token = getattr(getattr(sociallogin, "token", None), "token", "")
        if not token:
            return None
        wanted = settings.SSO_REQUIRED_GROUPS
        try:
            with self.get_requests_session() as sess:
                response = sess.post(
                    GRAPH_CHECK_MEMBER_GROUPS,
                    json={"groupIds": wanted},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
            if response.status_code != 200:
                logger.warning("SSO: checkMemberGroups returned HTTP %s", response.status_code)
                return None
            found = {str(g).lower() for g in response.json().get("value", [])}
        except Exception as exc:  # network error, bad JSON
            logger.warning("SSO: checkMemberGroups failed: %s", exc.__class__.__name__)
            return None
        return bool(found & set(wanted))

    def _refuse(self, request, sociallogin, reason: str, message: str) -> None:
        """Stop the login: log why, tell the user, go back to the login page."""
        logger.warning("SSO login refused (%s) for Microsoft account %s",
                       reason, sociallogin.account.uid)
        messages.error(request, message)
        raise ImmediateHttpResponse(redirect("login"))


def _domain_allowed(email: str) -> bool:
    """True when the address's domain is in SSO_ALLOWED_EMAIL_DOMAINS."""
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1]
    return domain in {d.strip().lower() for d in settings.SSO_ALLOWED_EMAIL_DOMAINS if d.strip()}
