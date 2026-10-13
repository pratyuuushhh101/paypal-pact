"""AppConfig for custom user domain."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """User application configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.users"
    label: str = "users"
    verbose_name: str = "Users"
