"""AppConfig for escrow application."""

from django.apps import AppConfig


class EscrowConfig(AppConfig):
    """Configuration class for the Escrow app."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "escrow"
    verbose_name: str = "Escrow Engine"
