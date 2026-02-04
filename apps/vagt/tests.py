"""
Tests for the Vagt (shift management) application.

Tests the simplified board model where Controllers have a direct status.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Controller, StatusLog, PersonalAccessToken

User = get_user_model()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def create_user(username="testuser", password="testpass123", **kwargs):
    """Create and return a test user."""
    return User.objects.create_user(username=username, password=password, **kwargs)


def create_controller(callsign="01", name="Test", **kwargs):
    """Create and return a test Controller."""
    return Controller.objects.create(callsign=callsign, name=name, **kwargs)


# =============================================================================
# CONTROLLER MODEL TESTS
# =============================================================================


class ControllerModelTests(TestCase):
    """Tests for the Controller model."""

    def test_create_controller(self):
        """Test creating a controller with required fields."""
        controller = Controller.objects.create(callsign="01", name="John")

        self.assertEqual(controller.callsign, "01")
        self.assertEqual(controller.name, "John")
        self.assertEqual(controller.status, Controller.Status.GAAET)
        self.assertTrue(controller.is_active)

    def test_str_returns_callsign_and_name(self):
        """Test string representation."""
        controller = create_controller(callsign="02", name="Jane")

        self.assertEqual(str(controller), "02 Jane")

    def test_str_includes_note(self):
        """Test string representation includes note if present."""
        controller = create_controller(callsign="03", name="Bob", note="Flex")

        self.assertEqual(str(controller), "03 Bob Flex")

    def test_set_status_changes_status(self):
        """Test set_status changes the controller status."""
        user = create_user()
        controller = create_controller()

        controller.set_status(Controller.Status.MOEDT, by_user=user)

        self.assertEqual(controller.status, Controller.Status.MOEDT)
        self.assertEqual(controller.status_changed_by, user)
        self.assertIsNotNone(controller.status_changed_at)

    def test_set_status_creates_log(self):
        """Test set_status creates a StatusLog entry."""
        user = create_user()
        controller = create_controller()

        controller.set_status(Controller.Status.MOEDT, by_user=user)

        logs = StatusLog.objects.filter(controller=controller)
        self.assertEqual(logs.count(), 1)

        log = logs.first()
        self.assertEqual(log.old_status, Controller.Status.GAAET)
        self.assertEqual(log.new_status, Controller.Status.MOEDT)
        self.assertEqual(log.changed_by, user)

    def test_set_status_same_status_no_change(self):
        """Test set_status does nothing if status is the same."""
        controller = create_controller()
        original_status = controller.status

        controller.set_status(original_status)

        logs = StatusLog.objects.filter(controller=controller)
        self.assertEqual(logs.count(), 0)

    def test_ordering_by_callsign(self):
        """Test controllers are ordered by callsign."""
        c2 = create_controller(callsign="02", name="B")
        c1 = create_controller(callsign="01", name="A")
        c3 = create_controller(callsign="03", name="C")

        controllers = list(Controller.objects.all())

        self.assertEqual(controllers[0], c1)
        self.assertEqual(controllers[1], c2)
        self.assertEqual(controllers[2], c3)


# =============================================================================
# STATUS LOG MODEL TESTS
# =============================================================================


class StatusLogModelTests(TestCase):
    """Tests for the StatusLog model."""

    def test_create_log(self):
        """Test creating a status log entry."""
        controller = create_controller()
        user = create_user()

        log = StatusLog.objects.create(
            controller=controller,
            changed_by=user,
            old_status=Controller.Status.GAAET,
            new_status=Controller.Status.MOEDT,
        )

        self.assertEqual(log.controller, controller)
        self.assertEqual(log.changed_by, user)
        self.assertIsNotNone(log.changed_at)

    def test_str_representation(self):
        """Test string representation."""
        controller = create_controller(name="Alice")
        log = StatusLog.objects.create(
            controller=controller,
            old_status=Controller.Status.GAAET,
            new_status=Controller.Status.MOEDT,
        )

        self.assertIn("Alice", str(log))
        self.assertIn("GAAET", str(log))
        self.assertIn("MOEDT", str(log))

    def test_ordering_by_changed_at_descending(self):
        """Test logs are ordered newest first."""
        controller = create_controller()

        log1 = StatusLog.objects.create(
            controller=controller,
            old_status=Controller.Status.GAAET,
            new_status=Controller.Status.MOEDT,
        )
        log2 = StatusLog.objects.create(
            controller=controller,
            old_status=Controller.Status.MOEDT,
            new_status=Controller.Status.GAAET,
        )

        logs = list(StatusLog.objects.filter(controller=controller))

        self.assertEqual(logs[0], log2)
        self.assertEqual(logs[1], log1)


# =============================================================================
# PERSONAL ACCESS TOKEN TESTS
# =============================================================================


class PersonalAccessTokenTests(TestCase):
    """Tests for the PersonalAccessToken model."""

    def test_issue_creates_token(self):
        """Test issue() creates a token and returns raw value."""
        user = create_user()

        token_obj, raw_token = PersonalAccessToken.issue(user=user, label="Test")

        self.assertIsNotNone(token_obj)
        self.assertIsNotNone(raw_token)
        self.assertEqual(token_obj.user, user)
        self.assertEqual(token_obj.label, "Test")

    def test_issue_with_ttl(self):
        """Test issue() with ttl_hours sets expiry."""
        user = create_user()

        token_obj, _ = PersonalAccessToken.issue(user=user, label="Test", ttl_hours=24)

        self.assertIsNotNone(token_obj.expires_at)

    def test_authenticate_valid_token(self):
        """Test authenticate_raw_token with valid token."""
        user = create_user()
        token_obj, raw_token = PersonalAccessToken.issue(user=user, label="Test")

        result = PersonalAccessToken.authenticate_raw_token(raw_token)

        self.assertIsNotNone(result)
        self.assertEqual(result.pk, token_obj.pk)

    def test_authenticate_invalid_token(self):
        """Test authenticate_raw_token with invalid token."""
        result = PersonalAccessToken.authenticate_raw_token("invalid-token")

        self.assertIsNone(result)

    def test_is_active_fresh_token(self):
        """Test is_active() returns True for fresh token."""
        user = create_user()
        token_obj, _ = PersonalAccessToken.issue(user=user, label="Test")

        self.assertTrue(token_obj.is_active())

    def test_is_active_revoked_token(self):
        """Test is_active() returns False for revoked token."""
        user = create_user()
        token_obj, _ = PersonalAccessToken.issue(user=user, label="Test")
        token_obj.revoked_at = timezone.now()
        token_obj.save()

        self.assertFalse(token_obj.is_active())

    def test_is_active_expired_token(self):
        """Test is_active() returns False for expired token."""
        user = create_user()
        token_obj, _ = PersonalAccessToken.issue(user=user, label="Test", ttl_hours=1)
        token_obj.expires_at = timezone.now() - timedelta(hours=1)
        token_obj.save()

        self.assertFalse(token_obj.is_active())


# =============================================================================
# VIEW TESTS
# =============================================================================


class BoardViewTests(TestCase):
    """Tests for the board view."""

    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.login(username="testuser", password="testpass123")

    def test_board_view_returns_200(self):
        """Board view returns 200 OK for logged in user."""
        response = self.client.get(reverse("vagt:board"))

        self.assertEqual(response.status_code, 200)

    def test_board_view_requires_login(self):
        """Board view redirects to login for anonymous user."""
        self.client.logout()

        response = self.client.get(reverse("vagt:board"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_board_view_shows_controllers(self):
        """Board view includes controllers in context."""
        controller = create_controller()

        response = self.client.get(reverse("vagt:board"))

        self.assertIn("controllers", response.context)


class SetStatusViewTests(TestCase):
    """Tests for the set_status view."""

    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.login(username="testuser", password="testpass123")
        self.controller = create_controller()

    def test_set_status_changes_controller_status(self):
        """POST to set_status changes the controller status."""
        url = reverse("vagt:set_status", kwargs={"pk": self.controller.pk})

        response = self.client.post(url, {"status": "MOEDT"})

        self.controller.refresh_from_db()
        self.assertEqual(self.controller.status, Controller.Status.MOEDT)
        self.assertEqual(response.status_code, 200)

    def test_set_status_requires_post(self):
        """GET request to set_status returns 405."""
        url = reverse("vagt:set_status", kwargs={"pk": self.controller.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)


class LogViewTests(TestCase):
    """Tests for the log view."""

    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.login(username="testuser", password="testpass123")

    def test_log_view_returns_200(self):
        """Log view returns 200 OK."""
        response = self.client.get(reverse("vagt:log"))

        self.assertEqual(response.status_code, 200)

    def test_log_view_includes_logs(self):
        """Log view includes logs in context."""
        response = self.client.get(reverse("vagt:log"))

        self.assertIn("logs", response.context)


# =============================================================================
# API TESTS
# =============================================================================


class HealthCheckAPITests(TestCase):
    """Tests for the health check endpoint."""

    def test_health_check_returns_200(self):
        """Health check endpoint returns 200."""
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
