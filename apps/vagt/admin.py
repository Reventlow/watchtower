"""Django admin configuration for vagt app."""

from django.contrib import admin

from .models import Controller, PersonalAccessToken, StatusLog


@admin.register(Controller)
class ControllerAdmin(admin.ModelAdmin):
    """Admin for managing controllers."""
    list_display = ["callsign", "name", "note", "status", "is_active"]
    list_filter = ["status", "is_active"]
    list_editable = ["status"]
    search_fields = ["callsign", "name"]
    ordering = ["callsign"]


@admin.register(StatusLog)
class StatusLogAdmin(admin.ModelAdmin):
    """Admin for viewing status logs (read-only)."""
    list_display = ["changed_at", "controller", "old_status", "new_status", "changed_by"]
    list_filter = ["new_status", "changed_at"]
    search_fields = ["controller__name", "controller__number"]
    readonly_fields = ["controller", "changed_by", "changed_at", "old_status", "new_status"]
    ordering = ["-changed_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PersonalAccessToken)
class PersonalAccessTokenAdmin(admin.ModelAdmin):
    """Admin for API tokens."""
    list_display = ["label", "user", "created_at", "expires_at", "last_used_at"]
    list_filter = ["user"]
    search_fields = ["label", "user__username"]
    readonly_fields = ["token_hash", "created_at", "last_used_at"]
