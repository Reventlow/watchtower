# models.py (Django 5.x) - Vagt board system
#
# Simple digital version of the physical magnetic board.
# Controllers have a status: FERIE | SYG | MØDT | GÅET

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Controller(models.Model):
    """
    A ticket controller on the board.
    Like a row on the physical board with a magnet in one column.
    """
    class Status(models.TextChoices):
        FERIE = "FERIE", "Ferie"
        SYG = "SYG", "Syg"
        MOEDT = "MOEDT", "Mødt"
        GAAET = "GAAET", "Gået"

    # Display info (matches physical board)
    callsign = models.CharField(max_length=10, unique=True)  # "01", "02" - used on radio
    name = models.CharField(max_length=120)  # "Theis", "Casper", etc.
    note = models.CharField(max_length=50, blank=True, default="")  # "Flex", etc.
    is_active = models.BooleanField(default=True)

    # Current status (the "magnet" position)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.GAAET)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_changes",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["callsign"]

    def __str__(self) -> str:
        s = f"{self.callsign} {self.name}"
        if self.note:
            s += f" {self.note}"
        return s

    def set_status(self, new_status: str, by_user=None) -> None:
        """Set status and log the change."""
        old_status = self.status
        if new_status == old_status:
            return

        self.status = new_status
        self.status_changed_at = timezone.now()
        self.status_changed_by = by_user
        self.save(update_fields=["status", "status_changed_at", "status_changed_by", "updated_at"])

        StatusLog.objects.create(
            controller=self,
            changed_by=by_user,
            old_status=old_status,
            new_status=new_status,
        )


class StatusLog(models.Model):
    """Audit trail for status changes."""
    controller = models.ForeignKey(Controller, on_delete=models.CASCADE, related_name="status_logs")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="controller_status_logs"
    )
    changed_at = models.DateTimeField(default=timezone.now)
    old_status = models.CharField(max_length=10, choices=Controller.Status.choices)
    new_status = models.CharField(max_length=10, choices=Controller.Status.choices)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self) -> str:
        return f"{self.controller.name}: {self.old_status} → {self.new_status}"


class PersonalAccessToken(models.Model):
    """Token auth for the REST API."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    label = models.CharField(max_length=80)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} - {self.label}"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and timezone.now() >= self.expires_at

    def is_active(self) -> bool:
        return not self.is_revoked and not self.is_expired

    @staticmethod
    def _hash(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @classmethod
    def issue(cls, *, user, label: str, ttl_hours: int | None = None) -> tuple["PersonalAccessToken", str]:
        raw = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(hours=ttl_hours) if ttl_hours else None
        obj = cls.objects.create(user=user, label=label, token_hash=cls._hash(raw), expires_at=expires_at)
        return obj, raw

    @classmethod
    def authenticate_raw_token(cls, raw_token: str) -> "PersonalAccessToken | None":
        tok = cls.objects.filter(token_hash=cls._hash(raw_token)).select_related("user").first()
        if not tok or not tok.is_active():
            return None
        tok.last_used_at = timezone.now()
        tok.save(update_fields=["last_used_at"])
        return tok
