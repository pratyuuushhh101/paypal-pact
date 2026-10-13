"""Custom user database models."""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import PactUserManager


class PactUser(AbstractBaseUser, PermissionsMixin):
    """Primary user entity identified uniquely by email."""

    email = models.EmailField(
        verbose_name="email address",
        unique=True,
        db_index=True,
        max_length=255,
    )
    is_active = models.BooleanField(
        verbose_name="active status",
        default=True,
    )
    is_staff = models.BooleanField(
        verbose_name="staff status",
        default=False,
    )
    created_at = models.DateTimeField(
        verbose_name="creation timestamp",
        default=timezone.now,
        editable=False,
    )

    objects: PactUserManager = PactUserManager()

    USERNAME_FIELD: str = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the string representation of the user."""
        return self.email
