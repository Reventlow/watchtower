"""Django app configuration for vagt app."""

from django.apps import AppConfig


class VagtConfig(AppConfig):
    """Configuration for the Vagt (shift management) application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.vagt"
    verbose_name = "Vagtplan"  # Danish: Shift Schedule

    def ready(self):
        """Initialize app when Django starts."""
        # Import signals here to ensure they're registered
        # from . import signals  # noqa: F401
        pass
