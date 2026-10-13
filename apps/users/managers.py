"""Model manager for email-based user authentication."""

from typing import TYPE_CHECKING, Any
from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from .models import PactUser


class PactUserManager(BaseUserManager["PactUser"]):
    """Custom user manager where email is the primary credential."""

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_attributes: Any,
    ) -> "PactUser":
        """Create and persist a standard user account."""
        if not email:
            raise ValueError("An email address must be provided.")

        normalized_email: str = self.normalize_email(email)
        extra_attributes.setdefault("is_active", True)
        extra_attributes.setdefault("is_staff", False)
        extra_attributes.setdefault("is_superuser", False)

        user: "PactUser" = self.model(email=normalized_email, **extra_attributes)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_attributes: Any,
    ) -> "PactUser":
        """Create and persist a superuser account."""
        extra_attributes.setdefault("is_staff", True)
        extra_attributes.setdefault("is_superuser", True)
        extra_attributes.setdefault("is_active", True)

        if extra_attributes.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_attributes.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_attributes)
