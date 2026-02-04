"""
Comprehensive tests for the Vagt (shift management) application.

This module tests:
- Model behavior and business logic
- View functionality (HTMX endpoints)
- API endpoints

Uses Django TestCase with pytest-django compatibility.
"""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from .models import (
    Controller,
    ControllerStatusLog,
    PersonalAccessToken,
    Shift,
    ShiftAssignment,
    ShiftWatchStaff,
)

User = get_user_model()


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================


def create_user(username="testuser", password="testpass123", **kwargs):
    """Create and return a test user."""
    return User.objects.create_user(username=username, password=password, **kwargs)


def create_controller(name="Test Controller", controller_type="", is_active=True, **kwargs):
    """Create and return a test Controller instance."""
    return Controller.objects.create(
        name=name,
        controller_type=controller_type,
        is_active=is_active,
        **kwargs,
    )


def create_shift(status_value=Shift.Status.OPEN, note="", **kwargs):
    """Create and return a test Shift instance."""
    return Shift.objects.create(
        status=status_value,
        note=note,
        **kwargs,
    )


def create_assignment(
    shift=None,
    controller=None,
    callsign="O1",
    status_value=ShiftAssignment.Status.UNKNOWN,
    **kwargs,
):
    """Create and return a test ShiftAssignment instance."""
    if shift is None:
        shift = create_shift()
    if controller is None:
        controller = create_controller()

    return ShiftAssignment.objects.create(
        shift=shift,
        controller=controller,
        callsign=callsign,
        status=status_value,
        **kwargs,
    )


def create_status_log(
    shift_assignment=None,
    changed_by=None,
    old_status=ShiftAssignment.Status.UNKNOWN,
    new_status=ShiftAssignment.Status.ON_DUTY,
    note="",
    **kwargs,
):
    """Create and return a test ControllerStatusLog instance."""
    if shift_assignment is None:
        shift_assignment = create_assignment()

    return ControllerStatusLog.objects.create(
        shift_assignment=shift_assignment,
        changed_by=changed_by,
        old_status=old_status,
        new_status=new_status,
        note=note,
        **kwargs,
    )


def create_token(user=None, label="Test Token", ttl_hours=None):
    """Create and return a PersonalAccessToken and its raw value."""
    if user is None:
        user = create_user()
    return PersonalAccessToken.issue(user=user, label=label, ttl_hours=ttl_hours)


# =============================================================================
# CONTROLLER MODEL TESTS
# =============================================================================


class ControllerModelTests(TestCase):
    """Tests for the Controller model."""

    def test_create_controller_with_required_fields(self):
        """Test creating a controller with only required fields."""
        controller = Controller.objects.create(name="John")

        self.assertEqual(controller.name, "John")
        self.assertEqual(controller.controller_type, "")
        self.assertTrue(controller.is_active)
        self.assertIsNotNone(controller.created_at)
        self.assertIsNotNone(controller.updated_at)

    def test_create_controller_with_all_fields(self):
        """Test creating a controller with all fields populated."""
        user = create_user()
        controller = Controller.objects.create(
            name="Jane",
            controller_type="Flex",
            is_active=False,
            created_by=user,
        )

        self.assertEqual(controller.name, "Jane")
        self.assertEqual(controller.controller_type, "Flex")
        self.assertFalse(controller.is_active)
        self.assertEqual(controller.created_by, user)

    def test_str_returns_name(self):
        """Test string representation returns the controller name."""
        controller = create_controller(name="Alice")

        self.assertEqual(str(controller), "Alice")

    def test_ordering_by_name_then_id(self):
        """Test that controllers are ordered by name, then by id."""
        controller_b = create_controller(name="Bob")
        controller_a = create_controller(name="Alice")
        controller_a2 = create_controller(name="Alice")

        controllers = list(Controller.objects.all())

        self.assertEqual(controllers[0], controller_a)
        self.assertEqual(controllers[1], controller_a2)
        self.assertEqual(controllers[2], controller_b)

    def test_created_by_null_on_user_delete(self):
        """Test that created_by is set to NULL when the user is deleted."""
        user = create_user(username="creator")
        controller = create_controller(name="Test", created_by=user)
        user.delete()

        controller.refresh_from_db()
        self.assertIsNone(controller.created_by)


# =============================================================================
# SHIFT MODEL TESTS
# =============================================================================


class ShiftModelTests(TestCase):
    """Tests for the Shift model."""

    def test_create_shift_default_values(self):
        """Test that a new shift has correct default values."""
        shift = Shift.objects.create()

        self.assertEqual(shift.status, Shift.Status.OPEN)
        self.assertIsNotNone(shift.opened_at)
        self.assertIsNone(shift.closed_at)
        self.assertEqual(shift.note, "")

    def test_str_returns_formatted_string(self):
        """Test string representation includes ID and status."""
        shift = create_shift()

        self.assertIn(str(shift.pk), str(shift))
        self.assertIn("OPEN", str(shift))

    def test_is_open_property_true_for_open_shift(self):
        """Test is_open property returns True for OPEN status."""
        shift = create_shift(status_value=Shift.Status.OPEN)

        self.assertTrue(shift.is_open)

    def test_is_open_property_false_for_closed_shift(self):
        """Test is_open property returns False for CLOSED status."""
        shift = create_shift(status_value=Shift.Status.CLOSED)

        self.assertFalse(shift.is_open)

    def test_ordering_by_opened_at_descending(self):
        """Test that shifts are ordered by opened_at descending (newest first)."""
        shift1 = create_shift()
        shift2 = create_shift()

        shifts = list(Shift.objects.all())

        # Shift2 created later should be first
        self.assertEqual(shifts[0], shift2)
        self.assertEqual(shifts[1], shift1)


class ShiftCanCloseTests(TestCase):
    """
    Tests for Shift.can_close() business rule.

    CRITICAL BUSINESS RULE:
    - Returns False if ANY assignment has status ON_DUTY or UNKNOWN
    - Returns True if ALL assignments are OFF_DUTY, SICK, or VACATION
    """

    def test_can_close_returns_true_for_shift_with_no_assignments(self):
        """An empty shift can be closed."""
        shift = create_shift()

        self.assertTrue(shift.can_close())

    def test_can_close_returns_false_with_on_duty_assignment(self):
        """Shift with ON_DUTY assignment cannot be closed."""
        shift = create_shift()
        controller = create_controller()
        create_assignment(
            shift=shift,
            controller=controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.ON_DUTY,
        )

        self.assertFalse(shift.can_close())

    def test_can_close_returns_false_with_unknown_assignment(self):
        """Shift with UNKNOWN assignment cannot be closed."""
        shift = create_shift()
        controller = create_controller()
        create_assignment(
            shift=shift,
            controller=controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.UNKNOWN,
        )

        self.assertFalse(shift.can_close())

    def test_can_close_returns_true_with_all_off_duty(self):
        """Shift with all OFF_DUTY assignments can be closed."""
        shift = create_shift()
        controller1 = create_controller(name="C1")
        controller2 = create_controller(name="C2")
        create_assignment(
            shift=shift,
            controller=controller1,
            callsign="O1",
            status_value=ShiftAssignment.Status.OFF_DUTY,
        )
        create_assignment(
            shift=shift,
            controller=controller2,
            callsign="O2",
            status_value=ShiftAssignment.Status.OFF_DUTY,
        )

        self.assertTrue(shift.can_close())

    def test_can_close_returns_true_with_sick_assignments(self):
        """Shift with SICK assignments can be closed."""
        shift = create_shift()
        controller = create_controller()
        create_assignment(
            shift=shift,
            controller=controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.SICK,
        )

        self.assertTrue(shift.can_close())

    def test_can_close_returns_true_with_vacation_assignments(self):
        """Shift with VACATION assignments can be closed."""
        shift = create_shift()
        controller = create_controller()
        create_assignment(
            shift=shift,
            controller=controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.VACATION,
        )

        self.assertTrue(shift.can_close())

    def test_can_close_returns_true_with_mixed_non_blocking_statuses(self):
        """Shift with mix of OFF_DUTY, SICK, VACATION can be closed."""
        shift = create_shift()
        controller1 = create_controller(name="C1")
        controller2 = create_controller(name="C2")
        controller3 = create_controller(name="C3")

        create_assignment(
            shift=shift,
            controller=controller1,
            callsign="O1",
            status_value=ShiftAssignment.Status.OFF_DUTY,
        )
        create_assignment(
            shift=shift,
            controller=controller2,
            callsign="O2",
            status_value=ShiftAssignment.Status.SICK,
        )
        create_assignment(
            shift=shift,
            controller=controller3,
            callsign="O3",
            status_value=ShiftAssignment.Status.VACATION,
        )

        self.assertTrue(shift.can_close())

    def test_can_close_returns_false_with_single_blocking_among_many(self):
        """
        Shift cannot close if even one assignment is blocking.

        This tests the edge case where most assignments are non-blocking
        but one ON_DUTY or UNKNOWN should still block closure.
        """
        shift = create_shift()
        controller1 = create_controller(name="C1")
        controller2 = create_controller(name="C2")
        controller3 = create_controller(name="C3")

        create_assignment(
            shift=shift,
            controller=controller1,
            callsign="O1",
            status_value=ShiftAssignment.Status.OFF_DUTY,
        )
        create_assignment(
            shift=shift,
            controller=controller2,
            callsign="O2",
            status_value=ShiftAssignment.Status.SICK,
        )
        # This one blocking assignment should prevent closure
        create_assignment(
            shift=shift,
            controller=controller3,
            callsign="O3",
            status_value=ShiftAssignment.Status.ON_DUTY,
        )

        self.assertFalse(shift.can_close())


class ShiftCloseTests(TestCase):
    """Tests for Shift.close() method."""

    def test_close_raises_valueerror_when_not_closable(self):
        """Shift.close() raises ValueError if shift cannot be closed."""
        shift = create_shift()
        controller = create_controller()
        create_assignment(
            shift=shift,
            controller=controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.ON_DUTY,
        )

        with self.assertRaises(ValueError) as context:
            shift.close()

        self.assertIn("cannot be closed", str(context.exception))

    def test_close_sets_status_to_closed(self):
        """Shift.close() sets status to CLOSED."""
        shift = create_shift()

        shift.close()

        self.assertEqual(shift.status, Shift.Status.CLOSED)

    def test_close_sets_closed_at_timestamp(self):
        """Shift.close() sets closed_at to current time."""
        shift = create_shift()

        before = timezone.now()
        shift.close()
        after = timezone.now()

        self.assertIsNotNone(shift.closed_at)
        self.assertGreaterEqual(shift.closed_at, before)
        self.assertLessEqual(shift.closed_at, after)

    def test_close_persists_to_database(self):
        """Shift.close() saves changes to the database."""
        shift = create_shift()
        shift.close()

        # Reload from database
        shift.refresh_from_db()

        self.assertEqual(shift.status, Shift.Status.CLOSED)
        self.assertIsNotNone(shift.closed_at)


# =============================================================================
# SHIFT ASSIGNMENT MODEL TESTS
# =============================================================================


class ShiftAssignmentModelTests(TestCase):
    """Tests for the ShiftAssignment model."""

    def test_create_assignment_with_required_fields(self):
        """Test creating an assignment with required fields."""
        shift = create_shift()
        controller = create_controller()

        assignment = ShiftAssignment.objects.create(
            shift=shift,
            controller=controller,
            callsign="O1",
        )

        self.assertEqual(assignment.shift, shift)
        self.assertEqual(assignment.controller, controller)
        self.assertEqual(assignment.callsign, "O1")
        self.assertEqual(assignment.status, ShiftAssignment.Status.UNKNOWN)

    def test_str_returns_formatted_string(self):
        """Test string representation includes callsign, name, and status."""
        controller = create_controller(name="Alice")
        assignment = create_assignment(
            controller=controller,
            callsign="O5",
            status_value=ShiftAssignment.Status.ON_DUTY,
        )

        result = str(assignment)

        self.assertIn("O5", result)
        self.assertIn("Alice", result)
        self.assertIn("ON_DUTY", result)

    def test_ordering_by_callsign_then_id(self):
        """Test that assignments are ordered by callsign, then id."""
        shift = create_shift()
        controller1 = create_controller(name="C1")
        controller2 = create_controller(name="C2")
        controller3 = create_controller(name="C3")

        a3 = create_assignment(shift=shift, controller=controller1, callsign="O3")
        a1 = create_assignment(shift=shift, controller=controller2, callsign="O1")
        a2 = create_assignment(shift=shift, controller=controller3, callsign="O2")

        assignments = list(ShiftAssignment.objects.filter(shift=shift))

        self.assertEqual(assignments[0], a1)
        self.assertEqual(assignments[1], a2)
        self.assertEqual(assignments[2], a3)


class ShiftAssignmentUniqueConstraintTests(TestCase):
    """
    Tests for the unique callsign per shift constraint.

    BUSINESS RULE: Callsign must be unique within a shift.
    """

    def test_duplicate_callsign_same_shift_raises_integrity_error(self):
        """Cannot create two assignments with the same callsign in one shift."""
        shift = create_shift()
        controller1 = create_controller(name="C1")
        controller2 = create_controller(name="C2")

        create_assignment(shift=shift, controller=controller1, callsign="O1")

        with self.assertRaises(IntegrityError):
            create_assignment(shift=shift, controller=controller2, callsign="O1")

    def test_same_callsign_different_shifts_allowed(self):
        """Same callsign can be used in different shifts."""
        shift1 = create_shift()
        shift2 = create_shift()
        controller1 = create_controller(name="C1")
        controller2 = create_controller(name="C2")

        a1 = create_assignment(shift=shift1, controller=controller1, callsign="O1")
        a2 = create_assignment(shift=shift2, controller=controller2, callsign="O1")

        self.assertEqual(a1.callsign, a2.callsign)
        self.assertNotEqual(a1.shift, a2.shift)


class ShiftAssignmentSetStatusTests(TestCase):
    """
    Tests for ShiftAssignment.set_status() method.

    BUSINESS RULE: set_status() must create an audit log entry.
    """

    def test_set_status_changes_status(self):
        """set_status() changes the assignment status."""
        user = create_user()
        assignment = create_assignment(status_value=ShiftAssignment.Status.UNKNOWN)

        assignment.set_status(ShiftAssignment.Status.ON_DUTY, by_user=user)

        self.assertEqual(assignment.status, ShiftAssignment.Status.ON_DUTY)

    def test_set_status_creates_audit_log(self):
        """set_status() creates a ControllerStatusLog entry."""
        user = create_user()
        assignment = create_assignment(status_value=ShiftAssignment.Status.UNKNOWN)

        assignment.set_status(ShiftAssignment.Status.ON_DUTY, by_user=user)

        logs = ControllerStatusLog.objects.filter(shift_assignment=assignment)
        self.assertEqual(logs.count(), 1)

        log = logs.first()
        self.assertEqual(log.old_status, ShiftAssignment.Status.UNKNOWN)
        self.assertEqual(log.new_status, ShiftAssignment.Status.ON_DUTY)
        self.assertEqual(log.changed_by, user)

    def test_set_status_updates_last_changed_fields(self):
        """set_status() updates last_changed_at and last_changed_by."""
        user = create_user()
        assignment = create_assignment()

        before = timezone.now()
        assignment.set_status(ShiftAssignment.Status.ON_DUTY, by_user=user)
        after = timezone.now()

        self.assertIsNotNone(assignment.last_changed_at)
        self.assertGreaterEqual(assignment.last_changed_at, before)
        self.assertLessEqual(assignment.last_changed_at, after)
        self.assertEqual(assignment.last_changed_by, user)

    def test_set_status_no_change_if_same_status(self):
        """set_status() does nothing if new status equals current status."""
        user = create_user()
        assignment = create_assignment(status_value=ShiftAssignment.Status.ON_DUTY)

        assignment.set_status(ShiftAssignment.Status.ON_DUTY, by_user=user)

        # No log should be created
        logs = ControllerStatusLog.objects.filter(shift_assignment=assignment)
        self.assertEqual(logs.count(), 0)

    def test_set_status_appends_note(self):
        """set_status() with note appends to assignment note."""
        user = create_user()
        assignment = create_assignment(status_value=ShiftAssignment.Status.UNKNOWN, note="Initial")

        assignment.set_status(
            ShiftAssignment.Status.ON_DUTY,
            by_user=user,
            note="Checked in at 08:00",
        )

        self.assertIn("Initial", assignment.note)
        self.assertIn("Checked in at 08:00", assignment.note)

    def test_set_status_note_recorded_in_log(self):
        """set_status() note is stored in the audit log."""
        user = create_user()
        assignment = create_assignment()

        assignment.set_status(
            ShiftAssignment.Status.ON_DUTY,
            by_user=user,
            note="Test note",
        )

        log = ControllerStatusLog.objects.filter(shift_assignment=assignment).first()
        self.assertEqual(log.note, "Test note")

    def test_set_status_persists_to_database(self):
        """set_status() saves changes to the database."""
        user = create_user()
        assignment = create_assignment(status_value=ShiftAssignment.Status.UNKNOWN)

        assignment.set_status(ShiftAssignment.Status.OFF_DUTY, by_user=user)
        assignment.refresh_from_db()

        self.assertEqual(assignment.status, ShiftAssignment.Status.OFF_DUTY)

    def test_set_status_multiple_changes_creates_multiple_logs(self):
        """Multiple status changes create multiple log entries."""
        user = create_user()
        assignment = create_assignment(status_value=ShiftAssignment.Status.UNKNOWN)

        assignment.set_status(ShiftAssignment.Status.ON_DUTY, by_user=user)
        assignment.set_status(ShiftAssignment.Status.OFF_DUTY, by_user=user)

        logs = ControllerStatusLog.objects.filter(shift_assignment=assignment).order_by("changed_at")
        self.assertEqual(logs.count(), 2)

        # First log: UNKNOWN -> ON_DUTY
        self.assertEqual(logs[0].old_status, ShiftAssignment.Status.UNKNOWN)
        self.assertEqual(logs[0].new_status, ShiftAssignment.Status.ON_DUTY)

        # Second log: ON_DUTY -> OFF_DUTY
        self.assertEqual(logs[1].old_status, ShiftAssignment.Status.ON_DUTY)
        self.assertEqual(logs[1].new_status, ShiftAssignment.Status.OFF_DUTY)


# =============================================================================
# CONTROLLER STATUS LOG MODEL TESTS
# =============================================================================


class ControllerStatusLogModelTests(TestCase):
    """Tests for the ControllerStatusLog model."""

    def test_create_log_entry(self):
        """Test creating an audit log entry."""
        assignment = create_assignment(callsign="O5")
        user = create_user()

        log = ControllerStatusLog.objects.create(
            shift_assignment=assignment,
            changed_by=user,
            old_status=ShiftAssignment.Status.UNKNOWN,
            new_status=ShiftAssignment.Status.ON_DUTY,
            note="Test note",
        )

        self.assertEqual(log.shift_assignment, assignment)
        self.assertEqual(log.changed_by, user)
        self.assertEqual(log.old_status, ShiftAssignment.Status.UNKNOWN)
        self.assertEqual(log.new_status, ShiftAssignment.Status.ON_DUTY)
        self.assertEqual(log.note, "Test note")
        self.assertIsNotNone(log.changed_at)

    def test_str_returns_formatted_string(self):
        """Test string representation shows callsign and status transition."""
        assignment = create_assignment(callsign="O3")
        log = create_status_log(
            shift_assignment=assignment,
            old_status=ShiftAssignment.Status.UNKNOWN,
            new_status=ShiftAssignment.Status.ON_DUTY,
        )

        result = str(log)

        self.assertIn("O3", result)
        self.assertIn("UNKNOWN", result)
        self.assertIn("ON_DUTY", result)

    def test_ordering_by_changed_at_descending(self):
        """Test that logs are ordered by changed_at descending (newest first)."""
        assignment = create_assignment()

        log1 = create_status_log(shift_assignment=assignment)
        log2 = create_status_log(shift_assignment=assignment)

        logs = list(ControllerStatusLog.objects.filter(shift_assignment=assignment))

        # Log2 created later should be first
        self.assertEqual(logs[0], log2)
        self.assertEqual(logs[1], log1)

    def test_changed_by_null_on_user_delete(self):
        """Test that changed_by is set to NULL when the user is deleted."""
        user = create_user(username="logger")
        log = create_status_log(changed_by=user)
        user.delete()

        log.refresh_from_db()
        self.assertIsNone(log.changed_by)

    def test_log_cascade_deletes_with_assignment(self):
        """Test that logs are deleted when the assignment is deleted."""
        assignment = create_assignment()
        create_status_log(shift_assignment=assignment)
        assignment_pk = assignment.pk

        self.assertEqual(ControllerStatusLog.objects.filter(shift_assignment__pk=assignment_pk).count(), 1)

        assignment.delete()

        self.assertEqual(ControllerStatusLog.objects.filter(shift_assignment__pk=assignment_pk).count(), 0)


# =============================================================================
# PERSONAL ACCESS TOKEN MODEL TESTS
# =============================================================================


class PersonalAccessTokenModelTests(TestCase):
    """Tests for the PersonalAccessToken model."""

    def test_issue_creates_token_and_returns_raw_value(self):
        """Test that issue() creates a token and returns the raw value."""
        user = create_user()

        token_obj, raw_token = PersonalAccessToken.issue(
            user=user,
            label="Test Token",
        )

        self.assertIsNotNone(token_obj)
        self.assertIsNotNone(raw_token)
        self.assertEqual(token_obj.user, user)
        self.assertEqual(token_obj.label, "Test Token")
        self.assertIsNone(token_obj.expires_at)
        self.assertIsNone(token_obj.revoked_at)

    def test_issue_with_ttl_sets_expiry(self):
        """Test that issue() with ttl_hours sets correct expiry."""
        user = create_user()

        before = timezone.now()
        token_obj, _ = PersonalAccessToken.issue(
            user=user,
            label="Expiring Token",
            ttl_hours=24,
        )
        after = timezone.now()

        self.assertIsNotNone(token_obj.expires_at)
        expected_min = before + timedelta(hours=24)
        expected_max = after + timedelta(hours=24)
        self.assertGreaterEqual(token_obj.expires_at, expected_min)
        self.assertLessEqual(token_obj.expires_at, expected_max)

    def test_token_hash_is_sha256_of_raw_token(self):
        """Test that the stored hash is SHA-256 of the raw token."""
        import hashlib

        user = create_user()
        token_obj, raw_token = PersonalAccessToken.issue(user=user, label="Test")

        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        self.assertEqual(token_obj.token_hash, expected_hash)

    def test_raw_token_not_stored(self):
        """Test that the raw token is not stored in the database."""
        user = create_user()
        token_obj, raw_token = PersonalAccessToken.issue(user=user, label="Test")

        # Raw token should not appear in any field
        self.assertNotEqual(token_obj.token_hash, raw_token)
        self.assertNotIn(raw_token, token_obj.label)


class PersonalAccessTokenIsActiveTests(TestCase):
    """Tests for PersonalAccessToken.is_active() method."""

    def test_is_active_returns_true_for_fresh_token(self):
        """Fresh token is active."""
        token_obj, _ = create_token()

        self.assertTrue(token_obj.is_active())

    def test_is_active_returns_false_for_revoked_token(self):
        """Revoked token is not active."""
        token_obj, _ = create_token()
        token_obj.revoke()

        self.assertFalse(token_obj.is_active())

    def test_is_active_returns_false_for_expired_token(self):
        """Expired token is not active."""
        user = create_user()
        token_obj, _ = PersonalAccessToken.issue(
            user=user,
            label="Short-lived",
            ttl_hours=1,
        )
        # Set expiry to the past
        token_obj.expires_at = timezone.now() - timedelta(hours=1)
        token_obj.save()

        self.assertFalse(token_obj.is_active())

    def test_is_revoked_property(self):
        """Test is_revoked property."""
        token_obj, _ = create_token()

        self.assertFalse(token_obj.is_revoked)

        token_obj.revoke()

        self.assertTrue(token_obj.is_revoked)

    def test_is_expired_property_for_non_expiring_token(self):
        """Test is_expired property returns False for tokens without expiry."""
        token_obj, _ = create_token()

        self.assertFalse(token_obj.is_expired)

    def test_is_expired_property_for_future_expiry(self):
        """Test is_expired property returns False for future expiry."""
        user = create_user()
        token_obj, _ = PersonalAccessToken.issue(
            user=user,
            label="Future",
            ttl_hours=24,
        )

        self.assertFalse(token_obj.is_expired)

    def test_is_expired_property_for_past_expiry(self):
        """Test is_expired property returns True for past expiry."""
        user = create_user()
        token_obj, _ = PersonalAccessToken.issue(
            user=user,
            label="Expired",
            ttl_hours=1,
        )
        token_obj.expires_at = timezone.now() - timedelta(hours=1)
        token_obj.save()

        self.assertTrue(token_obj.is_expired)


class PersonalAccessTokenRevokeTests(TestCase):
    """Tests for PersonalAccessToken.revoke() method."""

    def test_revoke_sets_revoked_at(self):
        """revoke() sets revoked_at timestamp."""
        token_obj, _ = create_token()

        self.assertIsNone(token_obj.revoked_at)

        before = timezone.now()
        token_obj.revoke()
        after = timezone.now()

        self.assertIsNotNone(token_obj.revoked_at)
        self.assertGreaterEqual(token_obj.revoked_at, before)
        self.assertLessEqual(token_obj.revoked_at, after)

    def test_revoke_is_idempotent(self):
        """Multiple revoke() calls do not change the original timestamp."""
        token_obj, _ = create_token()
        token_obj.revoke()
        first_revoked_at = token_obj.revoked_at

        token_obj.revoke()

        self.assertEqual(token_obj.revoked_at, first_revoked_at)


class PersonalAccessTokenRotateTests(TestCase):
    """Tests for PersonalAccessToken.rotate() method."""

    def test_rotate_returns_new_raw_token(self):
        """rotate() returns a new raw token."""
        token_obj, old_raw = create_token()

        new_raw = token_obj.rotate()

        self.assertIsNotNone(new_raw)
        self.assertNotEqual(new_raw, old_raw)

    def test_rotate_updates_hash(self):
        """rotate() updates the token hash."""
        token_obj, _ = create_token()
        old_hash = token_obj.token_hash

        token_obj.rotate()

        self.assertNotEqual(token_obj.token_hash, old_hash)

    def test_rotate_clears_revoked_at(self):
        """rotate() clears revoked_at (un-revokes the token)."""
        token_obj, _ = create_token()
        token_obj.revoke()

        self.assertIsNotNone(token_obj.revoked_at)

        token_obj.rotate()

        self.assertIsNone(token_obj.revoked_at)

    def test_rotate_with_ttl_sets_new_expiry(self):
        """rotate() with ttl_hours sets new expiry."""
        token_obj, _ = create_token()

        self.assertIsNone(token_obj.expires_at)

        before = timezone.now()
        token_obj.rotate(ttl_hours=48)
        after = timezone.now()

        expected_min = before + timedelta(hours=48)
        expected_max = after + timedelta(hours=48)
        self.assertGreaterEqual(token_obj.expires_at, expected_min)
        self.assertLessEqual(token_obj.expires_at, expected_max)


class PersonalAccessTokenAuthenticateTests(TestCase):
    """Tests for PersonalAccessToken.authenticate_raw_token() method."""

    def test_authenticate_valid_token(self):
        """authenticate_raw_token() returns token for valid raw token."""
        token_obj, raw_token = create_token()

        result = PersonalAccessToken.authenticate_raw_token(raw_token)

        self.assertIsNotNone(result)
        self.assertEqual(result.pk, token_obj.pk)

    def test_authenticate_updates_last_used_at(self):
        """authenticate_raw_token() updates last_used_at timestamp."""
        token_obj, raw_token = create_token()

        self.assertIsNone(token_obj.last_used_at)

        before = timezone.now()
        PersonalAccessToken.authenticate_raw_token(raw_token)
        after = timezone.now()

        token_obj.refresh_from_db()
        self.assertIsNotNone(token_obj.last_used_at)
        self.assertGreaterEqual(token_obj.last_used_at, before)
        self.assertLessEqual(token_obj.last_used_at, after)

    def test_authenticate_invalid_token_returns_none(self):
        """authenticate_raw_token() returns None for invalid token."""
        create_token()

        result = PersonalAccessToken.authenticate_raw_token("invalid-token-here")

        self.assertIsNone(result)

    def test_authenticate_revoked_token_returns_none(self):
        """authenticate_raw_token() returns None for revoked token."""
        token_obj, raw_token = create_token()
        token_obj.revoke()

        result = PersonalAccessToken.authenticate_raw_token(raw_token)

        self.assertIsNone(result)

    def test_authenticate_expired_token_returns_none(self):
        """authenticate_raw_token() returns None for expired token."""
        user = create_user()
        token_obj, raw_token = PersonalAccessToken.issue(
            user=user,
            label="Expired",
            ttl_hours=1,
        )
        token_obj.expires_at = timezone.now() - timedelta(hours=1)
        token_obj.save()

        result = PersonalAccessToken.authenticate_raw_token(raw_token)

        self.assertIsNone(result)


# =============================================================================
# VIEW TESTS
# =============================================================================


class BoardViewTests(TestCase):
    """Tests for the board_view."""

    def setUp(self):
        """Set up test client and user."""
        self.client = Client()
        self.user = create_user()
        self.client.login(username="testuser", password="testpass123")

    def test_board_view_returns_200(self):
        """Board view returns 200 OK."""
        response = self.client.get(reverse("vagt:board"))

        self.assertEqual(response.status_code, 200)

    def test_board_view_with_no_shifts(self):
        """Board view handles no shifts gracefully."""
        response = self.client.get(reverse("vagt:board"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get("shift"))

    def test_board_view_shows_open_shift(self):
        """Board view displays the current open shift."""
        shift = create_shift(status_value=Shift.Status.OPEN)

        response = self.client.get(reverse("vagt:board"))

        self.assertEqual(response.context["shift"], shift)

    def test_board_view_shows_assignments(self):
        """Board view includes shift assignments."""
        shift = create_shift()
        controller = create_controller(name="Alice")
        assignment = create_assignment(
            shift=shift,
            controller=controller,
            callsign="O1",
        )

        response = self.client.get(reverse("vagt:board"))

        assignments = response.context["assignments"]
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]["assignment"], assignment)

    def test_board_view_shows_blocking_count(self):
        """Board view includes correct blocking count."""
        shift = create_shift()
        controller1 = create_controller(name="C1")
        controller2 = create_controller(name="C2")

        create_assignment(
            shift=shift,
            controller=controller1,
            callsign="O1",
            status_value=ShiftAssignment.Status.ON_DUTY,
        )
        create_assignment(
            shift=shift,
            controller=controller2,
            callsign="O2",
            status_value=ShiftAssignment.Status.OFF_DUTY,
        )

        response = self.client.get(reverse("vagt:board"))

        self.assertEqual(response.context["blocking_count"], 1)

    def test_board_view_can_close_shift_flag(self):
        """Board view includes can_close_shift flag."""
        shift = create_shift()
        controller = create_controller()
        create_assignment(
            shift=shift,
            controller=controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.OFF_DUTY,
        )

        response = self.client.get(reverse("vagt:board"))

        self.assertTrue(response.context["can_close_shift"])

    def test_board_view_htmx_request_returns_partial(self):
        """HTMX request returns partial template."""
        create_shift()

        response = self.client.get(
            reverse("vagt:board"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        # HTMX requests should return the partial
        self.assertIn("assignments", response.context)

    def test_board_view_shows_most_recent_closed_shift_if_no_open(self):
        """Board view shows most recent closed shift if no open shift exists."""
        closed_shift = create_shift(status_value=Shift.Status.CLOSED)

        response = self.client.get(reverse("vagt:board"))

        self.assertEqual(response.context["shift"], closed_shift)


class UpdateStatusViewTests(TestCase):
    """Tests for the update_status view."""

    def setUp(self):
        """Set up test client and test data."""
        self.client = Client()
        self.user = create_user()
        self.client.login(username="testuser", password="testpass123")

        self.shift = create_shift()
        self.controller = create_controller()
        self.assignment = create_assignment(
            shift=self.shift,
            controller=self.controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.UNKNOWN,
        )

    def test_update_status_changes_assignment_status(self):
        """POST to update_status changes the assignment status."""
        url = reverse("vagt:update_status", kwargs={"pk": self.assignment.pk})

        response = self.client.post(url, {"status": ShiftAssignment.Status.ON_DUTY})

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ShiftAssignment.Status.ON_DUTY)
        self.assertEqual(response.status_code, 200)

    def test_update_status_creates_audit_log(self):
        """update_status creates an audit log entry."""
        url = reverse("vagt:update_status", kwargs={"pk": self.assignment.pk})

        self.client.post(url, {"status": ShiftAssignment.Status.ON_DUTY})

        logs = ControllerStatusLog.objects.filter(shift_assignment=self.assignment)
        self.assertEqual(logs.count(), 1)

    def test_update_status_requires_post(self):
        """GET request to update_status returns 405."""
        url = reverse("vagt:update_status", kwargs={"pk": self.assignment.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)

    def test_update_status_invalid_status_returns_400(self):
        """Invalid status value returns 400."""
        url = reverse("vagt:update_status", kwargs={"pk": self.assignment.pk})

        response = self.client.post(url, {"status": "INVALID_STATUS"})

        self.assertEqual(response.status_code, 400)

    def test_update_status_nonexistent_assignment_returns_404(self):
        """Nonexistent assignment returns 404."""
        url = reverse("vagt:update_status", kwargs={"pk": 99999})

        response = self.client.post(url, {"status": ShiftAssignment.Status.ON_DUTY})

        self.assertEqual(response.status_code, 404)

    def test_update_status_same_status_no_log_created(self):
        """Setting same status does not create a new log entry."""
        self.assignment.status = ShiftAssignment.Status.ON_DUTY
        self.assignment.save()

        url = reverse("vagt:update_status", kwargs={"pk": self.assignment.pk})
        self.client.post(url, {"status": ShiftAssignment.Status.ON_DUTY})

        logs = ControllerStatusLog.objects.filter(shift_assignment=self.assignment)
        self.assertEqual(logs.count(), 0)


class UndoStatusViewTests(TestCase):
    """Tests for the undo_status view."""

    def setUp(self):
        """Set up test client and test data."""
        self.client = Client()
        self.user = create_user()
        self.client.login(username="testuser", password="testpass123")

        self.shift = create_shift()
        self.controller = create_controller()
        self.assignment = create_assignment(
            shift=self.shift,
            controller=self.controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.UNKNOWN,
        )

    def test_undo_status_reverts_within_window(self):
        """undo_status reverts status change within the undo window."""
        # Make a status change
        self.assignment.set_status(ShiftAssignment.Status.ON_DUTY, by_user=self.user)

        url = reverse("vagt:undo_status", kwargs={"pk": self.assignment.pk})
        response = self.client.post(url)

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ShiftAssignment.Status.UNKNOWN)
        self.assertEqual(response.status_code, 200)

    def test_undo_status_deletes_log_entry(self):
        """undo_status deletes the log entry that was undone."""
        self.assignment.set_status(ShiftAssignment.Status.ON_DUTY, by_user=self.user)

        self.assertEqual(
            ControllerStatusLog.objects.filter(shift_assignment=self.assignment).count(),
            1,
        )

        url = reverse("vagt:undo_status", kwargs={"pk": self.assignment.pk})
        self.client.post(url)

        self.assertEqual(
            ControllerStatusLog.objects.filter(shift_assignment=self.assignment).count(),
            0,
        )

    def test_undo_status_clears_last_changed_at(self):
        """undo_status clears last_changed_at to prevent further undos."""
        self.assignment.set_status(ShiftAssignment.Status.ON_DUTY, by_user=self.user)

        url = reverse("vagt:undo_status", kwargs={"pk": self.assignment.pk})
        self.client.post(url)

        self.assignment.refresh_from_db()
        self.assertIsNone(self.assignment.last_changed_at)

    def test_undo_status_expired_window_no_change(self):
        """undo_status does not revert after window expires."""
        # Make a status change
        self.assignment.set_status(ShiftAssignment.Status.ON_DUTY, by_user=self.user)

        # Set last_changed_at to beyond the undo window (20+ seconds ago)
        self.assignment.last_changed_at = timezone.now() - timedelta(seconds=25)
        self.assignment.save()

        url = reverse("vagt:undo_status", kwargs={"pk": self.assignment.pk})
        self.client.post(url)

        self.assignment.refresh_from_db()
        # Status should remain ON_DUTY
        self.assertEqual(self.assignment.status, ShiftAssignment.Status.ON_DUTY)

    def test_undo_status_requires_post(self):
        """GET request to undo_status returns 405."""
        url = reverse("vagt:undo_status", kwargs={"pk": self.assignment.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)


class GetAuditInfoViewTests(TestCase):
    """Tests for the get_audit_info view."""

    def setUp(self):
        """Set up test client and test data."""
        self.client = Client()
        self.user = create_user()
        self.client.login(username="testuser", password="testpass123")

        self.shift = create_shift()
        self.controller = create_controller()
        self.assignment = create_assignment(
            shift=self.shift,
            controller=self.controller,
            callsign="O1",
        )

    def test_get_audit_info_returns_200(self):
        """get_audit_info returns 200 OK."""
        url = reverse("vagt:audit_info", kwargs={"pk": self.assignment.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

    def test_get_audit_info_includes_assignment(self):
        """get_audit_info includes the assignment in context."""
        url = reverse("vagt:audit_info", kwargs={"pk": self.assignment.pk})

        response = self.client.get(url)

        self.assertEqual(response.context["assignment"], self.assignment)

    def test_get_audit_info_includes_logs(self):
        """get_audit_info includes status logs in context."""
        create_status_log(
            shift_assignment=self.assignment,
            changed_by=self.user,
            old_status=ShiftAssignment.Status.UNKNOWN,
            new_status=ShiftAssignment.Status.ON_DUTY,
        )

        url = reverse("vagt:audit_info", kwargs={"pk": self.assignment.pk})
        response = self.client.get(url)

        logs = response.context["logs"]
        self.assertEqual(len(logs), 1)

    def test_get_audit_info_limits_to_5_logs(self):
        """get_audit_info returns at most 5 log entries."""
        for i in range(7):
            create_status_log(shift_assignment=self.assignment)

        url = reverse("vagt:audit_info", kwargs={"pk": self.assignment.pk})
        response = self.client.get(url)

        logs = response.context["logs"]
        self.assertEqual(len(logs), 5)

    def test_get_audit_info_nonexistent_assignment_returns_404(self):
        """Nonexistent assignment returns 404."""
        url = reverse("vagt:audit_info", kwargs={"pk": 99999})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)


# =============================================================================
# API TESTS
# =============================================================================


class APIAuthenticationTests(TestCase):
    """Tests for API token authentication."""

    def setUp(self):
        """Set up API client and test data."""
        self.client = APIClient()
        self.user = create_user()

    def test_unauthenticated_request_returns_401_or_403(self):
        """Unauthenticated request to protected endpoint returns 401 or 403."""
        response = self.client.get("/api/v1/controllers/")

        # DRF returns 401 for missing auth, 403 for invalid auth
        self.assertIn(response.status_code, [401, 403])

    def test_valid_token_authentication(self):
        """Valid token grants access to protected endpoint."""
        token_obj, raw_token = create_token(user=self.user)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")
        response = self.client.get("/api/v1/controllers/")

        self.assertEqual(response.status_code, 200)

    def test_invalid_token_returns_401(self):
        """Invalid token returns 401."""
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
        response = self.client.get("/api/v1/controllers/")

        self.assertEqual(response.status_code, 401)

    def test_revoked_token_returns_401(self):
        """Revoked token returns 401."""
        token_obj, raw_token = create_token(user=self.user)
        token_obj.revoke()

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")
        response = self.client.get("/api/v1/controllers/")

        self.assertEqual(response.status_code, 401)

    def test_expired_token_returns_401(self):
        """Expired token returns 401."""
        token_obj, raw_token = PersonalAccessToken.issue(
            user=self.user,
            label="Expired",
            ttl_hours=1,
        )
        token_obj.expires_at = timezone.now() - timedelta(hours=1)
        token_obj.save()

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")
        response = self.client.get("/api/v1/controllers/")

        self.assertEqual(response.status_code, 401)

    def test_health_check_public(self):
        """Health check endpoint is public."""
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "healthy")


class ControllerListAPITests(TestCase):
    """Tests for GET /api/v1/controllers/"""

    def setUp(self):
        """Set up authenticated API client."""
        self.client = APIClient()
        self.user = create_user()
        token_obj, raw_token = create_token(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

    def test_get_controllers_returns_active_only(self):
        """GET /api/v1/controllers/ returns only active controllers."""
        active = create_controller(name="Active", is_active=True)
        inactive = create_controller(name="Inactive", is_active=False)

        response = self.client.get("/api/v1/controllers/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Active")

    def test_get_controllers_filter_by_type(self):
        """GET /api/v1/controllers/?type=Flex filters by controller type."""
        flex = create_controller(name="Flex1", controller_type="Flex")
        regular = create_controller(name="Regular", controller_type="Regular")

        response = self.client.get("/api/v1/controllers/", {"type": "Flex"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Flex1")

    def test_get_controllers_ordered_by_name(self):
        """Controllers are ordered by name."""
        create_controller(name="Zebra")
        create_controller(name="Alpha")

        response = self.client.get("/api/v1/controllers/")

        names = [c["name"] for c in response.data["results"]]
        self.assertEqual(names, ["Alpha", "Zebra"])


class CurrentShiftAPITests(TestCase):
    """Tests for GET /api/v1/shifts/current/"""

    def setUp(self):
        """Set up authenticated API client."""
        self.client = APIClient()
        self.user = create_user()
        token_obj, raw_token = create_token(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

    def test_get_current_shift_returns_open_shift(self):
        """GET /api/v1/shifts/current/ returns the open shift."""
        shift = create_shift(status_value=Shift.Status.OPEN)

        response = self.client.get("/api/v1/shifts/current/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], shift.pk)
        self.assertEqual(response.data["status"], Shift.Status.OPEN)

    def test_get_current_shift_404_when_no_open_shift(self):
        """GET /api/v1/shifts/current/ returns 404 when no open shift."""
        create_shift(status_value=Shift.Status.CLOSED)

        response = self.client.get("/api/v1/shifts/current/")

        self.assertEqual(response.status_code, 404)
        self.assertIn("No open shift", response.data["detail"])

    def test_get_current_shift_includes_assignments(self):
        """Current shift response includes assignments."""
        shift = create_shift()
        controller = create_controller()
        assignment = create_assignment(
            shift=shift,
            controller=controller,
            callsign="O1",
        )

        response = self.client.get("/api/v1/shifts/current/")

        self.assertIn("assignments", response.data)
        self.assertEqual(len(response.data["assignments"]), 1)
        self.assertEqual(response.data["assignments"][0]["callsign"], "O1")


class ShiftAssignmentsAPITests(TestCase):
    """Tests for GET /api/v1/shifts/{id}/assignments/"""

    def setUp(self):
        """Set up authenticated API client."""
        self.client = APIClient()
        self.user = create_user()
        token_obj, raw_token = create_token(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

        self.shift = create_shift()
        self.controller = create_controller()

    def test_get_shift_assignments(self):
        """GET /api/v1/shifts/{id}/assignments/ returns assignments."""
        assignment = create_assignment(
            shift=self.shift,
            controller=self.controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.ON_DUTY,
        )

        response = self.client.get(f"/api/v1/shifts/{self.shift.pk}/assignments/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["callsign"], "O1")

    def test_get_shift_assignments_includes_blocking_count(self):
        """Response includes blocking_count."""
        controller2 = create_controller(name="C2")
        create_assignment(
            shift=self.shift,
            controller=self.controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.ON_DUTY,
        )
        create_assignment(
            shift=self.shift,
            controller=controller2,
            callsign="O2",
            status_value=ShiftAssignment.Status.OFF_DUTY,
        )

        response = self.client.get(f"/api/v1/shifts/{self.shift.pk}/assignments/")

        self.assertEqual(response.data["blocking_count"], 1)

    def test_get_shift_assignments_includes_can_close(self):
        """Response includes can_close flag."""
        create_assignment(
            shift=self.shift,
            controller=self.controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.OFF_DUTY,
        )

        response = self.client.get(f"/api/v1/shifts/{self.shift.pk}/assignments/")

        self.assertTrue(response.data["can_close"])

    def test_get_shift_assignments_filter_by_status(self):
        """Filter assignments by status."""
        controller2 = create_controller(name="C2")
        create_assignment(
            shift=self.shift,
            controller=self.controller,
            callsign="O1",
            status_value=ShiftAssignment.Status.ON_DUTY,
        )
        create_assignment(
            shift=self.shift,
            controller=controller2,
            callsign="O2",
            status_value=ShiftAssignment.Status.OFF_DUTY,
        )

        response = self.client.get(
            f"/api/v1/shifts/{self.shift.pk}/assignments/",
            {"status": "ON_DUTY"},
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["status"], "ON_DUTY")

    def test_get_shift_assignments_404_for_nonexistent_shift(self):
        """Returns 404 for nonexistent shift."""
        response = self.client.get("/api/v1/shifts/99999/assignments/")

        self.assertEqual(response.status_code, 404)


class ShiftStatusLogAPITests(TestCase):
    """Tests for GET /api/v1/shifts/{id}/status-log/"""

    def setUp(self):
        """Set up authenticated API client."""
        self.client = APIClient()
        self.user = create_user()
        token_obj, raw_token = create_token(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

        self.shift = create_shift()
        self.controller = create_controller()
        self.assignment = create_assignment(
            shift=self.shift,
            controller=self.controller,
            callsign="O1",
        )

    def test_get_status_log(self):
        """GET /api/v1/shifts/{id}/status-log/ returns audit log."""
        create_status_log(
            shift_assignment=self.assignment,
            changed_by=self.user,
            old_status=ShiftAssignment.Status.UNKNOWN,
            new_status=ShiftAssignment.Status.ON_DUTY,
        )

        response = self.client.get(f"/api/v1/shifts/{self.shift.pk}/status-log/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["old_status"], "UNKNOWN")
        self.assertEqual(response.data["results"][0]["new_status"], "ON_DUTY")

    def test_get_status_log_includes_callsign(self):
        """Log entries include callsign."""
        create_status_log(shift_assignment=self.assignment)

        response = self.client.get(f"/api/v1/shifts/{self.shift.pk}/status-log/")

        self.assertEqual(response.data["results"][0]["callsign"], "O1")

    def test_get_status_log_limit(self):
        """Status log respects limit parameter."""
        for i in range(10):
            create_status_log(shift_assignment=self.assignment)

        response = self.client.get(
            f"/api/v1/shifts/{self.shift.pk}/status-log/",
            {"limit": 5},
        )

        self.assertEqual(response.data["count"], 5)

    def test_get_status_log_404_for_nonexistent_shift(self):
        """Returns 404 for nonexistent shift."""
        response = self.client.get("/api/v1/shifts/99999/status-log/")

        self.assertEqual(response.status_code, 404)


class ShiftListAPITests(TestCase):
    """Tests for GET /api/v1/shifts/"""

    def setUp(self):
        """Set up authenticated API client."""
        self.client = APIClient()
        self.user = create_user()
        token_obj, raw_token = create_token(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

    def test_get_shifts_list(self):
        """GET /api/v1/shifts/ returns list of shifts."""
        shift1 = create_shift()
        shift2 = create_shift()

        response = self.client.get("/api/v1/shifts/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_get_shifts_filter_by_status(self):
        """Filter shifts by status."""
        open_shift = create_shift(status_value=Shift.Status.OPEN)
        closed_shift = create_shift(status_value=Shift.Status.CLOSED)

        response = self.client.get("/api/v1/shifts/", {"status": "CLOSED"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["status"], "CLOSED")

    def test_get_shifts_limit(self):
        """Shifts list respects limit parameter."""
        for i in range(15):
            create_shift()

        response = self.client.get("/api/v1/shifts/", {"limit": 5})

        self.assertEqual(response.data["count"], 5)

    def test_get_shifts_ordered_by_opened_at_descending(self):
        """Shifts are ordered by opened_at descending."""
        shift1 = create_shift()
        shift2 = create_shift()

        response = self.client.get("/api/v1/shifts/")

        # Shift2 created later should be first
        self.assertEqual(response.data["results"][0]["id"], shift2.pk)


class ShiftDetailAPITests(TestCase):
    """Tests for GET /api/v1/shifts/{id}/"""

    def setUp(self):
        """Set up authenticated API client."""
        self.client = APIClient()
        self.user = create_user()
        token_obj, raw_token = create_token(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")

    def test_get_shift_detail(self):
        """GET /api/v1/shifts/{id}/ returns shift details."""
        shift = create_shift(note="Test note")

        response = self.client.get(f"/api/v1/shifts/{shift.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], shift.pk)
        self.assertEqual(response.data["note"], "Test note")

    def test_get_shift_detail_includes_assignments(self):
        """Shift detail includes assignments."""
        shift = create_shift()
        controller = create_controller()
        create_assignment(
            shift=shift,
            controller=controller,
            callsign="O1",
        )

        response = self.client.get(f"/api/v1/shifts/{shift.pk}/")

        self.assertIn("assignments", response.data)
        self.assertEqual(len(response.data["assignments"]), 1)

    def test_get_shift_detail_404_for_nonexistent(self):
        """Returns 404 for nonexistent shift."""
        response = self.client.get("/api/v1/shifts/99999/")

        self.assertEqual(response.status_code, 404)


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================


class HelperFunctionTests(TestCase):
    """Tests for view helper functions."""

    def test_get_status_display_info_returns_dict(self):
        """get_status_display_info returns a dictionary with required keys."""
        from .views import get_status_display_info

        info = get_status_display_info(ShiftAssignment.Status.ON_DUTY)

        self.assertIn("label", info)
        self.assertIn("bg_class", info)
        self.assertIn("text_class", info)
        self.assertIn("border_class", info)
        self.assertIn("btn_class", info)
        self.assertIn("is_blocking", info)

    def test_get_status_display_info_on_duty_is_blocking(self):
        """ON_DUTY status is marked as blocking."""
        from .views import get_status_display_info

        info = get_status_display_info(ShiftAssignment.Status.ON_DUTY)

        self.assertTrue(info["is_blocking"])

    def test_get_status_display_info_unknown_is_blocking(self):
        """UNKNOWN status is marked as blocking."""
        from .views import get_status_display_info

        info = get_status_display_info(ShiftAssignment.Status.UNKNOWN)

        self.assertTrue(info["is_blocking"])

    def test_get_status_display_info_off_duty_not_blocking(self):
        """OFF_DUTY status is not blocking."""
        from .views import get_status_display_info

        info = get_status_display_info(ShiftAssignment.Status.OFF_DUTY)

        self.assertFalse(info["is_blocking"])

    def test_get_all_statuses_returns_list(self):
        """get_all_statuses returns a list of all status choices."""
        from .views import get_all_statuses

        statuses = get_all_statuses()

        self.assertEqual(len(statuses), 5)  # VACATION, SICK, ON_DUTY, OFF_DUTY, UNKNOWN
        values = [s["value"] for s in statuses]
        self.assertIn(ShiftAssignment.Status.ON_DUTY, values)
        self.assertIn(ShiftAssignment.Status.OFF_DUTY, values)

    def test_can_undo_assignment_within_window(self):
        """can_undo_assignment returns True within the undo window."""
        from .views import can_undo_assignment

        assignment = create_assignment()
        assignment.last_changed_at = timezone.now()

        self.assertTrue(can_undo_assignment(assignment))

    def test_can_undo_assignment_expired_window(self):
        """can_undo_assignment returns False after window expires."""
        from .views import can_undo_assignment

        assignment = create_assignment()
        assignment.last_changed_at = timezone.now() - timedelta(seconds=25)

        self.assertFalse(can_undo_assignment(assignment))

    def test_can_undo_assignment_no_last_changed(self):
        """can_undo_assignment returns False if last_changed_at is None."""
        from .views import can_undo_assignment

        assignment = create_assignment()
        assignment.last_changed_at = None

        self.assertFalse(can_undo_assignment(assignment))

    def test_get_undo_remaining_seconds(self):
        """get_undo_remaining_seconds returns correct remaining time."""
        from .views import get_undo_remaining_seconds

        assignment = create_assignment()
        assignment.last_changed_at = timezone.now()

        remaining = get_undo_remaining_seconds(assignment)

        # Should be close to 20 seconds (within a reasonable margin)
        self.assertGreater(remaining, 15)
        self.assertLessEqual(remaining, 20)

    def test_get_undo_remaining_seconds_expired(self):
        """get_undo_remaining_seconds returns 0 after window expires."""
        from .views import get_undo_remaining_seconds

        assignment = create_assignment()
        assignment.last_changed_at = timezone.now() - timedelta(seconds=25)

        remaining = get_undo_remaining_seconds(assignment)

        self.assertEqual(remaining, 0)
