"""
Pytest configuration and shared fixtures for the Watchtower project.

This module provides reusable fixtures for testing Django models, views, and API endpoints.
Fixtures are designed to work with pytest-django.
"""

import pytest
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from rest_framework.test import APIClient


User = get_user_model()


# =============================================================================
# USER FIXTURES
# =============================================================================


@pytest.fixture
def user(db):
    """Create and return a standard test user."""
    return User.objects.create_user(
        username="testuser",
        password="testpass123",
        email="test@example.com",
    )


@pytest.fixture
def admin_user(db):
    """Create and return an admin/superuser."""
    return User.objects.create_superuser(
        username="admin",
        password="adminpass123",
        email="admin@example.com",
    )


@pytest.fixture
def another_user(db):
    """Create and return a second test user."""
    return User.objects.create_user(
        username="another",
        password="testpass123",
        email="another@example.com",
    )


# =============================================================================
# CLIENT FIXTURES
# =============================================================================


@pytest.fixture
def client():
    """Provide a Django test client."""
    return Client()


@pytest.fixture
def authenticated_client(client, user):
    """Provide a Django test client logged in as the test user."""
    client.login(username="testuser", password="testpass123")
    return client


@pytest.fixture
def api_client():
    """Provide a DRF API test client."""
    return APIClient()


@pytest.fixture
def authenticated_api_client(api_client, user):
    """Provide an authenticated API client using token auth."""
    from apps.vagt.models import PersonalAccessToken

    token_obj, raw_token = PersonalAccessToken.issue(
        user=user,
        label="Test Token",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")
    return api_client


# =============================================================================
# MODEL FIXTURES
# =============================================================================


@pytest.fixture
def controller(db):
    """Create and return a test Controller."""
    from apps.vagt.models import Controller

    return Controller.objects.create(
        name="Test Controller",
        controller_type="Regular",
        is_active=True,
    )


@pytest.fixture
def controller_flex(db):
    """Create and return a Flex-type Controller."""
    from apps.vagt.models import Controller

    return Controller.objects.create(
        name="Flex Controller",
        controller_type="Flex",
        is_active=True,
    )


@pytest.fixture
def inactive_controller(db):
    """Create and return an inactive Controller."""
    from apps.vagt.models import Controller

    return Controller.objects.create(
        name="Inactive Controller",
        controller_type="Regular",
        is_active=False,
    )


@pytest.fixture
def shift(db):
    """Create and return an open test Shift."""
    from apps.vagt.models import Shift

    return Shift.objects.create(
        status=Shift.Status.OPEN,
        note="Test shift",
    )


@pytest.fixture
def closed_shift(db):
    """Create and return a closed test Shift."""
    from apps.vagt.models import Shift

    return Shift.objects.create(
        status=Shift.Status.CLOSED,
        closed_at=timezone.now(),
        note="Closed test shift",
    )


@pytest.fixture
def assignment(db, shift, controller):
    """Create and return a test ShiftAssignment with UNKNOWN status."""
    from apps.vagt.models import ShiftAssignment

    return ShiftAssignment.objects.create(
        shift=shift,
        controller=controller,
        callsign="O1",
        status=ShiftAssignment.Status.UNKNOWN,
    )


@pytest.fixture
def on_duty_assignment(db, shift, controller):
    """Create and return a ShiftAssignment with ON_DUTY status."""
    from apps.vagt.models import ShiftAssignment

    return ShiftAssignment.objects.create(
        shift=shift,
        controller=controller,
        callsign="O1",
        status=ShiftAssignment.Status.ON_DUTY,
    )


@pytest.fixture
def off_duty_assignment(db, shift, controller):
    """Create and return a ShiftAssignment with OFF_DUTY status."""
    from apps.vagt.models import ShiftAssignment

    return ShiftAssignment.objects.create(
        shift=shift,
        controller=controller,
        callsign="O1",
        status=ShiftAssignment.Status.OFF_DUTY,
    )


@pytest.fixture
def status_log(db, assignment, user):
    """Create and return a test ControllerStatusLog."""
    from apps.vagt.models import ControllerStatusLog, ShiftAssignment

    return ControllerStatusLog.objects.create(
        shift_assignment=assignment,
        changed_by=user,
        old_status=ShiftAssignment.Status.UNKNOWN,
        new_status=ShiftAssignment.Status.ON_DUTY,
        note="Test log entry",
    )


@pytest.fixture
def access_token(db, user):
    """Create and return a PersonalAccessToken and its raw value as a tuple."""
    from apps.vagt.models import PersonalAccessToken

    return PersonalAccessToken.issue(
        user=user,
        label="Test Token",
    )


@pytest.fixture
def expiring_token(db, user):
    """Create and return a token with a 24-hour TTL."""
    from apps.vagt.models import PersonalAccessToken

    return PersonalAccessToken.issue(
        user=user,
        label="Expiring Token",
        ttl_hours=24,
    )


@pytest.fixture
def expired_token(db, user):
    """Create and return an already-expired token."""
    from apps.vagt.models import PersonalAccessToken

    token_obj, raw_token = PersonalAccessToken.issue(
        user=user,
        label="Expired Token",
        ttl_hours=1,
    )
    token_obj.expires_at = timezone.now() - timedelta(hours=1)
    token_obj.save()
    return token_obj, raw_token


@pytest.fixture
def revoked_token(db, user):
    """Create and return a revoked token."""
    from apps.vagt.models import PersonalAccessToken

    token_obj, raw_token = PersonalAccessToken.issue(
        user=user,
        label="Revoked Token",
    )
    token_obj.revoke()
    return token_obj, raw_token


# =============================================================================
# COMPLEX SCENARIO FIXTURES
# =============================================================================


@pytest.fixture
def shift_with_assignments(db, shift):
    """Create a shift with multiple assignments in various states."""
    from apps.vagt.models import Controller, ShiftAssignment

    c1 = Controller.objects.create(name="Controller 1", is_active=True)
    c2 = Controller.objects.create(name="Controller 2", is_active=True)
    c3 = Controller.objects.create(name="Controller 3", is_active=True)

    a1 = ShiftAssignment.objects.create(
        shift=shift, controller=c1, callsign="O1",
        status=ShiftAssignment.Status.ON_DUTY,
    )
    a2 = ShiftAssignment.objects.create(
        shift=shift, controller=c2, callsign="O2",
        status=ShiftAssignment.Status.OFF_DUTY,
    )
    a3 = ShiftAssignment.objects.create(
        shift=shift, controller=c3, callsign="O3",
        status=ShiftAssignment.Status.UNKNOWN,
    )

    return {
        "shift": shift,
        "controllers": [c1, c2, c3],
        "assignments": [a1, a2, a3],
    }


@pytest.fixture
def closable_shift(db):
    """Create a shift that can be closed (all assignments non-blocking)."""
    from apps.vagt.models import Controller, Shift, ShiftAssignment

    shift = Shift.objects.create(status=Shift.Status.OPEN)

    c1 = Controller.objects.create(name="Controller 1", is_active=True)
    c2 = Controller.objects.create(name="Controller 2", is_active=True)

    ShiftAssignment.objects.create(
        shift=shift, controller=c1, callsign="O1",
        status=ShiftAssignment.Status.OFF_DUTY,
    )
    ShiftAssignment.objects.create(
        shift=shift, controller=c2, callsign="O2",
        status=ShiftAssignment.Status.SICK,
    )

    return shift


@pytest.fixture
def non_closable_shift(db):
    """Create a shift that cannot be closed (has blocking assignments)."""
    from apps.vagt.models import Controller, Shift, ShiftAssignment

    shift = Shift.objects.create(status=Shift.Status.OPEN)

    c1 = Controller.objects.create(name="Controller 1", is_active=True)

    ShiftAssignment.objects.create(
        shift=shift, controller=c1, callsign="O1",
        status=ShiftAssignment.Status.ON_DUTY,
    )

    return shift


# =============================================================================
# UTILITY FIXTURES
# =============================================================================


@pytest.fixture
def freeze_time():
    """
    Fixture that provides a context manager for freezing time.

    Usage:
        def test_something(freeze_time):
            with freeze_time(timezone.now()):
                # Time is frozen here
                pass
    """
    from unittest.mock import patch

    class TimeFreezer:
        def __call__(self, frozen_time):
            return patch("django.utils.timezone.now", return_value=frozen_time)

    return TimeFreezer()
