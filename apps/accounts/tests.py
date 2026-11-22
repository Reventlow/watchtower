"""Microsoft (Entra) sign-in, as in Harbinger: who gets in, SSO_ONLY with
break-glass accounts, the Graph group check, and the settings guards.

All Microsoft and Graph traffic is faked; the tenant below is a dummy.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from allauth.core import context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin, SocialToken
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from .adapters import GRAPH_CHECK_MEMBER_GROUPS, AccountAdapter, SocialAccountAdapter
from .checks import sso_has_required_groups, sso_only_has_break_glass

User = get_user_model()

TENANT = "11111111-2222-4333-8444-555555555555"
GROUP = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
OTHER = "99999999-8888-4777-8666-555555555555"
PASSWORD = "Correct-horse-battery-9"
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Templates use {% static %}; the manifest only exists after collectstatic.
PLAIN_STATIC = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)

# SSO as it is configured in production (allauth looks the app up when it
# links an account or builds a login from Graph's answer).
SSO_ON = override_settings(
    SSO_ENABLED=True,
    SSO_ALLOWED_EMAIL_DOMAINS=["fynbus.dk"],
    SSO_ALLOW_GUESTS=False,
    SSO_AUTO_CREATE_USERS=False,
    SSO_REQUIRED_GROUPS=[],
    SOCIALACCOUNT_PROVIDERS={"microsoft": {"APP": {"client_id": "id", "secret": "secret"}, "TENANT": TENANT}},
)


def _request():
    """A request with session and messages, as allauth's views have."""
    request = RequestFactory().get("/allauth/microsoft/login/callback/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = AnonymousUser()
    return request


def _login(upn: str, mail: str | None = None, uid: str = "oid-1", token: str | None = "access-token") -> SocialLogin:
    """A sociallogin as the Microsoft provider builds it from Graph /me."""
    data = {"id": uid, "userPrincipalName": upn, "mail": mail if mail is not None else upn,
            "mailNickname": upn.split("@")[0]}
    login = SocialLogin(account=SocialAccount(provider="microsoft", uid=uid, extra_data=data),
                        user=User(username=data["mailNickname"], email=data["mail"]))
    if token:
        login.token = SocialToken(token=token)
    return login


def _messages(request) -> str:
    return " ".join(str(m) for m in get_messages(request))


def _import_settings(**env) -> subprocess.CompletedProcess:
    """Load the settings in a fresh interpreter with these variables."""
    full_env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.base",
                "DJANGO_SECRET_KEY": "test-secret-key", **env}
    return subprocess.run([sys.executable, "-c", "import django; django.setup()"], cwd=BASE_DIR,
                          env=full_env, capture_output=True, text=True, timeout=60, check=False)


class FakeResponse:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code = status
        self._body = body if body is not None else {"value": []}
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._body


class FakeSession:
    """Stands in for adapter.get_requests_session(); records the POSTs."""

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


# --- local sign-up -------------------------------------------------------------


@PLAIN_STATIC
class SignupClosedTests(TestCase):
    def test_allauth_signup_creates_no_account(self):
        response = self.client.post("/allauth/signup/", {
            "email": "x@evil.example", "username": "intruder",
            "password1": "Very-long-pass-123!", "password2": "Very-long-pass-123!"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))
        self.assertFalse(User.objects.filter(username="intruder").exists())

    def test_allauth_login_page_leads_to_vagts(self):
        response = self.client.get("/allauth/login/?next=/log/")
        self.assertEqual(response["Location"], "/login/?next=/log/")

    def test_microsoft_routes_lead_to_login_while_sso_is_off(self):
        response = self.client.post("/allauth/microsoft/login/")
        self.assertEqual(response["Location"], "/login/")

    def test_account_adapter_is_closed(self):
        self.assertIs(AccountAdapter().is_open_for_signup(RequestFactory().get("/")), False)


# --- who gets in through Microsoft ---------------------------------------------


@SSO_ON
class SocialAdapterTests(TestCase):
    def setUp(self):
        self.adapter = SocialAccountAdapter()

    def test_guest_is_refused(self):
        login = _login("someone_partner.dk#EXT#@fynbus.onmicrosoft.com", mail="someone@fynbus.dk")
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), login)

    @override_settings(SSO_ALLOW_GUESTS=True, SSO_AUTO_CREATE_USERS=True)
    def test_guest_allowed_when_switched_on(self):
        login = _login("someone_partner.dk#EXT#@fynbus.onmicrosoft.com", mail="someone@fynbus.dk")
        self.adapter.pre_social_login(_request(), login)  # no exception

    def test_foreign_domain_is_refused(self):
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), _login("mallory@evil.example"))

    def test_first_login_links_existing_user_by_address(self):
        jens = User.objects.create_user("jens", email="JENS@fynbus.dk", password=PASSWORD)
        self.adapter.pre_social_login(_request(), _login("jens@fynbus.dk", uid="oid-jens"))
        self.assertEqual(SocialAccount.objects.get(provider="microsoft", uid="oid-jens").user, jens)

    def test_inactive_user_is_not_linked(self):
        User.objects.create_user("old", email="old@fynbus.dk", is_active=False)
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), _login("old@fynbus.dk"))
        self.assertFalse(SocialAccount.objects.exists())

    def test_later_logins_use_the_object_id_not_the_address(self):
        jens = User.objects.create_user("jens", email="jens@fynbus.dk", password=PASSWORD)
        SocialAccount.objects.create(provider="microsoft", uid="oid-jens", user=jens)
        login = _login("jens@fynbus.dk", uid="oid-jens")
        login.lookup()
        self.assertTrue(login.is_existing)
        self.assertEqual(login.user, jens)
        self.adapter.pre_social_login(_request(), login)  # no exception, no re-link

    def test_ambiguous_address_is_refused(self):
        User.objects.create_user("a", email="shared@fynbus.dk")
        User.objects.create_user("b", email="shared@fynbus.dk")
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), _login("shared@fynbus.dk"))

    def test_unknown_account_is_refused_while_auto_create_is_off(self):
        request = _request()
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(request, _login("new.person@fynbus.dk"))
        self.assertIn("ingen Vagt-bruger", _messages(request))
        self.assertIs(self.adapter.is_open_for_signup(request, _login("new.person@fynbus.dk")), False)

    @override_settings(SSO_AUTO_CREATE_USERS=True)
    def test_new_user_is_created_when_auto_create_is_on(self):
        request = _request()
        login = _login("new.person@fynbus.dk", uid="oid-new")
        self.adapter.pre_social_login(request, login)
        self.assertIs(self.adapter.is_open_for_signup(request, login), True)
        user = self.adapter.save_user(request, login)
        self.assertFalse(user.is_staff or user.is_superuser)


# --- the Entra group check -----------------------------------------------------


# The outermost class decorator wins where two set the same setting.
@override_settings(SSO_REQUIRED_GROUPS=[GROUP], SSO_AUTO_CREATE_USERS=True)
@SSO_ON
class GroupCheckTests(TestCase):
    def setUp(self):
        self.adapter = SocialAccountAdapter()

    def _graph(self, **kwargs) -> FakeSession:
        session = FakeSession(**kwargs)
        patcher = mock.patch.object(SocialAccountAdapter, "get_requests_session", lambda adapter: session)
        patcher.start()
        self.addCleanup(patcher.stop)
        return session

    def test_member_gets_in_and_graph_is_asked_with_the_users_token(self):
        graph = self._graph(response=FakeResponse(body={"value": [GROUP.upper()]}))
        self.adapter.pre_social_login(_request(), _login("karen@fynbus.dk"))
        (url, kwargs), = graph.calls
        self.assertEqual(url, GRAPH_CHECK_MEMBER_GROUPS)
        self.assertEqual(kwargs["json"], {"groupIds": [GROUP]})
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer access-token")
        self.assertTrue(kwargs["timeout"])

    def test_account_outside_the_groups_is_refused(self):
        self._graph(response=FakeResponse(body={"value": []}))
        request = _request()
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(request, _login("someadmin@fynbus.dk"))
        self.assertIn("ikke adgang til Vagt", _messages(request))

    def test_membership_of_an_unrelated_group_does_not_count(self):
        self._graph(response=FakeResponse(body={"value": [OTHER]}))
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), _login("someadmin@fynbus.dk"))

    def test_existing_linked_user_is_checked_too(self):
        """Removing someone from the group in Entra locks them out at their
        next login, even though their Vagt user exists and is linked."""
        user = User.objects.create_user("lars", email="lars@fynbus.dk")
        SocialAccount.objects.create(provider="microsoft", uid="oid-lars", user=user)
        login = _login("lars@fynbus.dk", uid="oid-lars")
        login.lookup()
        self.assertTrue(login.is_existing)
        self._graph(response=FakeResponse(body={"value": []}))
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), login)

    def test_refused_when_graph_cannot_answer(self):
        for graph in (
            {"response": FakeResponse(status=403, body={"error": {"code": "Authorization_RequestDenied"}})},
            {"response": FakeResponse(status=503)},
            {"response": FakeResponse(bad_json=True)},
            {"error": ConnectionError("down")},
        ):
            with self.subTest(graph=graph):
                self._graph(**graph)
                request = _request()
                with self.assertRaises(ImmediateHttpResponse):
                    self.adapter.pre_social_login(request, _login("karen@fynbus.dk"))
                self.assertIn("kunne ikke tjekke din adgang", _messages(request))

    def test_refused_without_an_access_token(self):
        graph = self._graph(response=FakeResponse(body={"value": [GROUP]}))
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), _login("karen@fynbus.dk", token=None))
        self.assertEqual(graph.calls, [])

    @override_settings(SSO_REQUIRED_GROUPS=[])
    def test_no_graph_call_when_no_groups_are_required(self):
        with mock.patch.object(SocialAccountAdapter, "get_requests_session",
                               side_effect=AssertionError("Graph was asked")):
            self.adapter.pre_social_login(_request(), _login("karen@fynbus.dk"))

    def test_domain_is_checked_before_graph(self):
        graph = self._graph(response=FakeResponse(body={"value": [GROUP]}))
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), _login("mallory@evil.example"))
        self.assertEqual(graph.calls, [])

    # The whole allauth flow, as the OAuth callback runs it.

    def _complete(self, upn, uid, process="login"):
        from allauth.socialaccount.adapter import get_adapter
        from allauth.socialaccount.helpers import complete_social_login

        request = _request()
        provider = get_adapter().get_provider(request, "microsoft")
        data = {"id": uid, "userPrincipalName": upn, "mail": upn, "mailNickname": upn.split("@")[0],
                "displayName": "Test Person"}
        login = provider.sociallogin_from_response(request, data)
        login.token = SocialToken(token="access-token")
        login.state = {"process": process, "next": "/log/"}
        with context.request_context(request):
            response = complete_social_login(request, login)
        return request, response

    def test_flow_refuses_outsiders_without_a_session_or_user(self):
        for process in ("login", "connect"):
            with self.subTest(process=process):
                self._graph(response=FakeResponse(body={"value": []}))
                request, response = self._complete("outsider@fynbus.dk", "oid-outsider", process)
                self.assertEqual((response.status_code, response["Location"]), (302, "/login/"))
                self.assertNotIn("_auth_user_id", request.session)
                self.assertFalse(User.objects.filter(email="outsider@fynbus.dk").exists())
                self.assertFalse(SocialAccount.objects.filter(uid="oid-outsider").exists())

    def test_flow_lets_a_member_in(self):
        self._graph(response=FakeResponse(body={"value": [GROUP]}))
        request, response = self._complete("new.person@fynbus.dk", "oid-new")
        user = User.objects.get(email="new.person@fynbus.dk")
        self.assertEqual(str(request.session["_auth_user_id"]), str(user.pk))
        self.assertEqual(response["Location"], "/log/")

    def test_flow_links_an_existing_user_and_logs_them_in(self):
        jens = User.objects.create_user("jens", email="jens@fynbus.dk", password=PASSWORD)
        self._graph(response=FakeResponse(body={"value": [GROUP]}))
        request, _ = self._complete("jens@fynbus.dk", "oid-jens")
        self.assertEqual(str(request.session["_auth_user_id"]), str(jens.pk))
        self.assertEqual(User.objects.count(), 1)


# --- SSO_ONLY: passwords only for break-glass ------------------------------------


@PLAIN_STATIC
@override_settings(SSO_ONLY=True, SSO_BREAK_GLASS_USERS=["Breakglass"])
@SSO_ON
class SSOOnlyTests(TestCase):
    def setUp(self):
        self.anna = User.objects.create_user("anna", email="anna@fynbus.dk", password=PASSWORD)
        self.root = User.objects.create_superuser("root", email="root@fynbus.dk", password=PASSWORD)
        self.glass = User.objects.create_superuser("breakglass", email="bg@fynbus.dk", password=PASSWORD)

    def _logged_in(self) -> bool:
        return "_auth_user_id" in self.client.session

    def test_login_page_refuses_every_password_while_sso_is_on(self):
        """No username and password on Vagt's login page with SSO on: not
        for normal users, superusers or break-glass, with or without
        SSO_ONLY, and with or without the old ?local=1."""
        for sso_only in (True, False):
            for url in ("/login/", "/login/?local=1"):
                for name in ("anna", "root", "breakglass"):
                    with self.subTest(sso_only=sso_only, url=url, user=name), self.settings(SSO_ONLY=sso_only):
                        with mock.patch("apps.accounts.backends.PasswordBackend.authenticate",
                                        side_effect=AssertionError("password was checked")):
                            response = self.client.post(url, {"username": name, "password": PASSWORD})
                        self.assertEqual((response.status_code, response["Location"]), (302, "/login/"))
                        self.assertFalse(self._logged_in())
        html = self.client.get("/login/").content.decode()
        self.assertIn("Log ind med din FynBus Microsoft-konto.", html)

    def test_break_glass_may_use_password_at_admin_login_case_insensitively(self):
        self.client.post("/admin/login/", {"username": "breakglass", "password": PASSWORD, "next": "/admin/"})
        self.assertTrue(self._logged_in())
        self.assertEqual(self.client.get("/").status_code, 200)  # and reach the board

    @override_settings(SSO_ONLY=False)
    def test_admin_login_takes_any_staff_password_without_sso_only(self):
        self.client.post("/admin/login/", {"username": "root", "password": PASSWORD, "next": "/admin/"})
        self.assertTrue(self._logged_in())

    def test_admin_login_obeys_sso_only(self):
        self.client.post("/admin/login/", {"username": "root", "password": PASSWORD, "next": "/admin/"})
        self.assertFalse(self._logged_in())
        self.client.post("/admin/login/", {"username": "breakglass", "password": PASSWORD, "next": "/admin/"})
        self.assertTrue(self._logged_in())

    def test_allauth_backend_by_email_obeys_sso_only(self):
        request = RequestFactory().get("/")
        self.assertIsNone(authenticate(request, email="anna@fynbus.dk", password=PASSWORD))
        self.assertIsNone(authenticate(request, username="anna", password=PASSWORD))

    def test_sso_session_works_under_sso_only(self):
        """A Microsoft login ends with allauth logging the user in through
        the allauth backend; that session must hold on later requests."""
        SocialAccount.objects.create(user=self.anna, provider="microsoft", uid="oid-anna")
        self.client.force_login(self.anna, backend="apps.accounts.backends.AllauthPasswordBackend")
        self.assertEqual(self.client.get("/").status_code, 200)

    @override_settings(SSO_ENABLED=False, SSO_ONLY=False)
    def test_existing_session_survives_switching_sso_only_on(self):
        """The rule is checked at login only; it must not log everyone out on
        every request (Django restores the session user through the backend)."""
        self.client.force_login(self.anna, backend="apps.accounts.backends.PasswordBackend")
        with self.settings(SSO_ENABLED=True, SSO_ONLY=True):
            self.assertEqual(self.client.get("/").status_code, 200)

    def test_login_page_is_microsoft_only(self):
        for sso_only in (True, False):
            for url in ("/login/?next=/log/", "/login/?local=1&next=/log/"):
                with self.subTest(sso_only=sso_only, url=url), self.settings(SSO_ONLY=sso_only):
                    html = self.client.get(url).content.decode()
                    self.assertNotIn('name="password"', html)
                    self.assertNotIn('name="username"', html)
                    self.assertIn('action="/allauth/microsoft/login/"', html)
                    self.assertIn('name="next" value="/log/"', html)
                    self.assertIn("Log ind med Microsoft", html)

    def test_refusal_message_is_shown_on_the_login_page(self):
        """The adapter sends a refused user back to /login/ with a message;
        the login page must show it, or the user only sees the page again."""
        from django.contrib import messages as django_messages

        from .views import LoginView

        request = _request()
        request.path = "/login/"
        django_messages.error(request, "Din Microsoft-konto har ikke adgang til Vagt.")
        response = LoginView.as_view()(request)
        response.render()
        self.assertIn("Din Microsoft-konto har ikke adgang til Vagt.", response.content.decode())

    def test_profile_hides_password_change_for_sso_users(self):
        self.client.force_login(self.anna, backend="apps.accounts.backends.AllauthPasswordBackend")
        html = self.client.get("/profile/").content.decode()
        self.assertNotIn('name="old_password"', html)
        self.assertIn("Microsoft-konto", html)
        self.client.post("/profile/", {"old_password": PASSWORD, "new_password1": "Another-pass-456!",
                                       "new_password2": "Another-pass-456!"})
        self.anna.refresh_from_db()
        self.assertTrue(self.anna.check_password(PASSWORD))

    def test_profile_has_no_password_change_for_break_glass_either(self):
        """Break-glass accounts change their password in Django admin."""
        self.client.force_login(self.glass, backend="apps.accounts.backends.PasswordBackend")
        html = self.client.get("/profile/").content.decode()
        self.assertNotIn('name="old_password"', html)
        self.assertEqual(self.client.get("/admin/password_change/").status_code, 200)

    def test_user_admin_shows_who_is_linked(self):
        SocialAccount.objects.create(user=self.anna, provider="microsoft", uid="oid-anna")
        self.client.force_login(self.glass, backend="apps.accounts.backends.PasswordBackend")
        html = self.client.get("/admin/auth/user/").content.decode()
        self.assertIn("✓ Linked", html)
        self.assertIn("Break-glass", html)
        unlinked = self.client.get("/admin/auth/user/?sso=no").content.decode()
        self.assertIn("root", unlinked)
        self.assertNotIn(">anna<", unlinked)


@PLAIN_STATIC
class LoginPageWithoutSSOTests(TestCase):
    def test_only_the_password_form(self):
        html = self.client.get("/login/").content.decode()
        self.assertIn('name="password"', html)
        self.assertNotIn("Log ind med Microsoft", html)

    def test_password_login_works(self):
        User.objects.create_user("anna", password=PASSWORD)
        response = self.client.post("/login/", {"username": "anna", "password": PASSWORD})
        self.assertEqual(response["Location"], "/")
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_password_shows_the_form_again_with_an_error(self):
        User.objects.create_user("anna", password=PASSWORD)
        html = self.client.post("/login/?next=/log/", {"username": "anna", "password": "wrong"}).content.decode()
        self.assertIn('name="password"', html)
        self.assertIn("Forkert brugernavn eller adgangskode", html)

    def test_signed_in_user_is_sent_on(self):
        self.client.force_login(User.objects.create_user("anna"))
        self.assertEqual(self.client.get("/login/")["Location"], "/")

    def test_profile_keeps_password_change(self):
        self.client.force_login(User.objects.create_user("anna", password=PASSWORD))
        self.assertIn('name="old_password"', self.client.get("/profile/").content.decode())


# --- settings, checks and the site ---------------------------------------------------


class ChecksTests(SimpleTestCase):
    @override_settings(SSO_ONLY=True, SSO_BREAK_GLASS_USERS=[])
    def test_warns_without_break_glass(self):
        self.assertEqual([w.id for w in sso_only_has_break_glass(None)], ["accounts.W001"])
        with self.settings(SSO_BREAK_GLASS_USERS=["breakglass"]):
            self.assertEqual(sso_only_has_break_glass(None), [])

    @override_settings(SSO_ENABLED=True, SSO_REQUIRED_GROUPS=[])
    def test_warns_when_sso_is_on_without_required_groups(self):
        self.assertEqual([w.id for w in sso_has_required_groups(None)], ["accounts.W002"])
        with self.settings(SSO_REQUIRED_GROUPS=[GROUP]):
            self.assertEqual(sso_has_required_groups(None), [])
        with self.settings(SSO_ENABLED=False):
            self.assertEqual(sso_has_required_groups(None), [])

    def test_sso_accounts_get_no_confirmation_mail(self):
        from allauth.socialaccount import app_settings

        self.assertEqual(app_settings.EMAIL_VERIFICATION, "none")


SSO_ENV = {"VAGT_SSO_ENABLED": "1", "VAGT_SSO_TENANT_ID": TENANT,
           "VAGT_SSO_CLIENT_ID": "id", "VAGT_SSO_CLIENT_SECRET": "secret"}


class SettingsGuardTests(SimpleTestCase):
    """Each case starts a fresh interpreter, so these are slowish."""

    def test_starts_with_sso_and_group_ids_in_any_case(self):
        result = _import_settings(**SSO_ENV, VAGT_SSO_REQUIRED_GROUPS=f" {GROUP.upper()} , {OTHER}")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_refuses_to_start_without_a_tenant_guid(self):
        for tenant in ("", "common", "organizations", "fynbus.dk"):
            with self.subTest(tenant=tenant):
                result = _import_settings(**{**SSO_ENV, "VAGT_SSO_TENANT_ID": tenant})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("VAGT_SSO_TENANT_ID", result.stderr)

    def test_refuses_to_start_without_client_secret(self):
        result = _import_settings(**{**SSO_ENV, "VAGT_SSO_CLIENT_SECRET": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VAGT_SSO_CLIENT_ID", result.stderr)

    def test_refuses_to_start_with_bad_group_ids(self):
        for value in ("Vagt-Users", f"{GROUP},nope", ",".join([GROUP] * 21)):
            with self.subTest(value=value[:40]):
                result = _import_settings(**SSO_ENV, VAGT_SSO_REQUIRED_GROUPS=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("VAGT_SSO_REQUIRED_GROUPS", result.stderr)

    def test_sso_only_refuses_to_start_without_sso(self):
        result = _import_settings(VAGT_SSO_ONLY="1", VAGT_SSO_ENABLED="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VAGT_SSO_ONLY", result.stderr)


class SiteTests(TestCase):
    def test_site_is_named_after_vagt(self):
        site = Site.objects.get_current()
        self.assertEqual((site.domain, site.name), ("vagt.fynbus.net", "Vagt"))

    def test_migration_renames_only_the_placeholder(self):
        import importlib

        from django.apps import apps as global_apps
        from django.db import connection

        name_site = importlib.import_module("apps.accounts.migrations.0001_site_domain").name_site
        editor = connection.schema_editor()
        Site.objects.update(domain="example.com", name="example.com")
        name_site(global_apps, editor)
        self.assertEqual(Site.objects.get().domain, "vagt.fynbus.net")
        Site.objects.update(domain="intra.example.org", name="Intra")
        name_site(global_apps, editor)
        self.assertEqual(Site.objects.get().domain, "intra.example.org")

    def test_manage_check_is_clean_by_default(self):
        call_command("check")


# --- admin pages: never for a Microsoft (SSO) session ------------------------------


@PLAIN_STATIC
@SSO_ON
class AdminAccessTests(TestCase):
    """Django admin and the in-app superuser pages are for local logins only."""

    def setUp(self):
        self.root = User.objects.create_superuser("root", email="root@fynbus.dk", password=PASSWORD)

    def _sso_session(self, user):
        from .access import SSO_SESSION_KEY

        self.client.force_login(user, backend="apps.accounts.backends.AllauthPasswordBackend")
        session = self.client.session
        session[SSO_SESSION_KEY] = True
        session.save()

    def test_local_superuser_reaches_admin_and_docs(self):
        self.client.force_login(self.root, backend="apps.accounts.backends.PasswordBackend")
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(self.client.get("/docs/").status_code, 200)
        html = self.client.get("/").content.decode()
        self.assertIn('href="/admin/"', html)
        self.assertIn('href="/docs/"', html)

    def test_sso_superuser_is_kept_out_of_admin(self):
        self._sso_session(self.root)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/admin/login/"))
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 302)
        self.assertEqual(self.client.post("/admin/auth/user/add/", {}).status_code, 302)

    def test_sso_superuser_is_kept_out_of_docs(self):
        self._sso_session(self.root)
        self.assertEqual(self.client.get("/docs/")["Location"], "/")
        self.assertEqual(self.client.get("/docs/sso/")["Location"], "/")

    def test_sso_session_hides_admin_links_but_keeps_the_board(self):
        self._sso_session(self.root)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn('href="/admin/"', html)
        self.assertNotIn('href="/docs/"', html)
        self.assertEqual(self.client.get("/controllers/").status_code, 200)
        self.assertEqual(self.client.get("/log/").status_code, 200)

    def test_microsoft_login_marks_the_session(self):
        from allauth.socialaccount.adapter import get_adapter
        from allauth.socialaccount.helpers import complete_social_login

        from .access import SSO_SESSION_KEY, has_admin_access

        request = _request()
        provider = get_adapter().get_provider(request, "microsoft")
        login = provider.sociallogin_from_response(request, {
            "id": "oid-root", "userPrincipalName": "root@fynbus.dk", "mail": "root@fynbus.dk",
            "mailNickname": "root", "displayName": "Root"})
        login.token = SocialToken(token="access-token")
        login.state = {"process": "login", "next": "/"}
        with context.request_context(request):
            complete_social_login(request, login)
        self.assertEqual(str(request.session["_auth_user_id"]), str(self.root.pk))
        self.assertIs(request.session.get(SSO_SESSION_KEY), True)
        request.user = self.root
        self.assertFalse(has_admin_access(request))

    def test_password_login_clears_the_mark(self):
        """Signing in again with a password (Django admin's login page), in a
        browser that had an SSO session, gives a session without the mark."""
        from .access import SSO_SESSION_KEY

        self._sso_session(self.root)
        self.client.post("/admin/login/", {"username": "root", "password": PASSWORD, "next": "/admin/"})
        self.assertNotIn(SSO_SESSION_KEY, self.client.session)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_admin_login_page_does_not_let_an_sso_session_in(self):
        """Django admin's own login page: an SSO user can't use a password
        under SSO_ONLY, and a break-glass login there is a local session."""
        with self.settings(SSO_ONLY=True, SSO_BREAK_GLASS_USERS=["breakglass"]):
            self._sso_session(self.root)
            self.client.post("/admin/login/", {"username": "root", "password": PASSWORD, "next": "/admin/"})
            self.assertEqual(self.client.get("/admin/").status_code, 302)
            User.objects.create_superuser("breakglass", email="bg@fynbus.dk", password=PASSWORD)
            self.client.post("/admin/login/", {"username": "breakglass", "password": PASSWORD, "next": "/admin/"})
            self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_staff_without_superuser_has_no_docs(self):
        staff = User.objects.create_user("staff", password=PASSWORD, is_staff=True)
        self.client.force_login(staff, backend="apps.accounts.backends.PasswordBackend")
        self.assertEqual(self.client.get("/docs/")["Location"], "/")


# --- review fixes --------------------------------------------------------------------


@PLAIN_STATIC
@override_settings(SSO_ONLY=True, SSO_BREAK_GLASS_USERS=["breakglass"])
@SSO_ON
class LoginPageDetailTests(TestCase):
    def test_allauth_success_messages_are_dropped(self):
        from django.contrib import messages as django_messages

        request = _request()
        AccountAdapter().add_message(request, django_messages.SUCCESS, message="Logget ind som root")
        AccountAdapter().add_message(request, django_messages.ERROR, message="Fejl")
        self.assertEqual(_messages(request), "Fejl")

    def test_login_page_shows_only_errors(self):
        from django.contrib import messages as django_messages

        from .views import LoginView

        request = _request()
        request.path = "/login/"
        django_messages.success(request, "Logget ind som root")
        response = LoginView.as_view()(request)
        response.render()
        self.assertNotIn("Logget ind som root", response.content.decode())

    def test_django_password_reset_and_change_are_closed(self):
        for url in ("/password_reset/", "/password_reset/done/", "/password_change/",
                    "/password_change/done/", "/reset/MQ/set-password/", "/reset/done/"):
            with self.subTest(url=url):
                response = self.client.post(url, {"email": "bg@fynbus.dk"})
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/login/"))

    def test_profile_hides_password_change_without_a_usable_password(self):
        with self.settings(SSO_ONLY=False):
            user = User.objects.create_user("newbie", email="newbie@fynbus.dk")  # no password
            self.client.force_login(user, backend="apps.accounts.backends.AllauthPasswordBackend")
            html = self.client.get("/profile/").content.decode()
            self.assertNotIn('name="old_password"', html)


class SessionMigrationTests(TestCase):
    """0002 moves sessions from ModelBackend to PasswordBackend, so the
    deploy keeps everyone signed in."""

    def _migration(self):
        import importlib

        return importlib.import_module("apps.accounts.migrations.0002_sessions_to_password_backend")

    def test_old_sessions_are_moved_and_stay_signed_in(self):
        from django.apps import apps as global_apps
        from django.contrib.sessions.backends.db import SessionStore
        from django.db import connection

        user = User.objects.create_user("anna", password=PASSWORD)
        self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        key = self.client.session.session_key
        other = SessionStore()
        other["something"] = 1
        other.save()

        self._migration().forwards(global_apps, connection.schema_editor())

        self.assertEqual(SessionStore(session_key=key)["_auth_user_backend"],
                         "apps.accounts.backends.PasswordBackend")
        self.assertEqual(SessionStore(session_key=other.session_key)["something"], 1)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_backwards_restores_model_backend(self):
        from django.apps import apps as global_apps
        from django.contrib.sessions.backends.db import SessionStore
        from django.db import connection

        user = User.objects.create_user("anna", password=PASSWORD)
        self.client.force_login(user, backend="apps.accounts.backends.PasswordBackend")
        key = self.client.session.session_key
        self._migration().backwards(global_apps, connection.schema_editor())
        self.assertEqual(SessionStore(session_key=key)["_auth_user_backend"],
                         "django.contrib.auth.backends.ModelBackend")
