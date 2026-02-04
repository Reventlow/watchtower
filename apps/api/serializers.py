"""
Serializers for the REST API.

Provides read-only serializers for external systems to consume shift data.
"""

from rest_framework import serializers

from apps.vagt.models import (
    Controller,
    ControllerStatusLog,
    Shift,
    ShiftAssignment,
    ShiftWatchStaff,
)


class ControllerSerializer(serializers.ModelSerializer):
    """Serializer for Controller model (roster entry)."""

    class Meta:
        model = Controller
        fields = [
            "id",
            "name",
            "controller_type",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ShiftAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for ShiftAssignment with nested controller info."""

    controller_name = serializers.CharField(source="controller.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    last_changed_by_username = serializers.CharField(
        source="last_changed_by.username", read_only=True, allow_null=True
    )
    is_blocking = serializers.SerializerMethodField()

    class Meta:
        model = ShiftAssignment
        fields = [
            "id",
            "callsign",
            "controller",
            "controller_name",
            "status",
            "status_display",
            "is_blocking",
            "note",
            "last_changed_at",
            "last_changed_by",
            "last_changed_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_is_blocking(self, obj) -> bool:
        """Check if this assignment blocks shift closure."""
        return obj.status in [
            ShiftAssignment.Status.ON_DUTY,
            ShiftAssignment.Status.UNKNOWN,
        ]


class ShiftWatchStaffSerializer(serializers.ModelSerializer):
    """Serializer for watch staff on a shift."""

    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = ShiftWatchStaff
        fields = [
            "id",
            "user",
            "username",
            "full_name",
            "is_on_duty",
            "joined_at",
            "left_at",
        ]
        read_only_fields = fields

    def get_full_name(self, obj) -> str:
        """Get full name or username if not available."""
        full_name = obj.user.get_full_name()
        return full_name if full_name else obj.user.username


class ShiftSerializer(serializers.ModelSerializer):
    """Serializer for Shift with summary counts."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    assignment_count = serializers.SerializerMethodField()
    blocking_count = serializers.SerializerMethodField()
    can_close = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            "id",
            "status",
            "status_display",
            "opened_at",
            "closed_at",
            "note",
            "assignment_count",
            "blocking_count",
            "can_close",
        ]
        read_only_fields = fields

    def get_assignment_count(self, obj) -> int:
        """Total number of assignments in this shift."""
        return obj.assignments.count()

    def get_blocking_count(self, obj) -> int:
        """Number of assignments blocking shift closure."""
        return obj.assignments.filter(
            status__in=[ShiftAssignment.Status.ON_DUTY, ShiftAssignment.Status.UNKNOWN]
        ).count()

    def get_can_close(self, obj) -> bool:
        """Whether the shift can be closed."""
        return obj.can_close()


class ShiftDetailSerializer(ShiftSerializer):
    """Detailed shift serializer with assignments and watch staff."""

    assignments = ShiftAssignmentSerializer(many=True, read_only=True)
    watch_staff_entries = ShiftWatchStaffSerializer(
        source="watch_entries", many=True, read_only=True
    )

    class Meta(ShiftSerializer.Meta):
        fields = ShiftSerializer.Meta.fields + [
            "assignments",
            "watch_staff_entries",
        ]


class ControllerStatusLogSerializer(serializers.ModelSerializer):
    """Serializer for audit log entries."""

    callsign = serializers.CharField(source="shift_assignment.callsign", read_only=True)
    controller_name = serializers.CharField(
        source="shift_assignment.controller.name", read_only=True
    )
    old_status_display = serializers.SerializerMethodField()
    new_status_display = serializers.SerializerMethodField()
    changed_by_username = serializers.CharField(
        source="changed_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = ControllerStatusLog
        fields = [
            "id",
            "shift_assignment",
            "callsign",
            "controller_name",
            "old_status",
            "old_status_display",
            "new_status",
            "new_status_display",
            "changed_by",
            "changed_by_username",
            "changed_at",
            "note",
        ]
        read_only_fields = fields

    def get_old_status_display(self, obj) -> str:
        """Get display label for old status."""
        return dict(ShiftAssignment.Status.choices).get(obj.old_status, obj.old_status)

    def get_new_status_display(self, obj) -> str:
        """Get display label for new status."""
        return dict(ShiftAssignment.Status.choices).get(obj.new_status, obj.new_status)
