"""Serializers for user registration, authentication, and profile management."""

from typing import Any
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import PactUser


class RegisterSerializer(serializers.Serializer):
    """Serializer for validating and registering new user accounts."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value: str) -> str:
        """Ensure the email is not already registered in the system."""
        if PactUser.objects.filter(email=value).exists():
            raise ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Verify that password and password_confirm match."""
        if attrs.get("password") != attrs.get("password_confirm"):
            raise ValidationError("Passwords do not match.")
        return attrs

    def create(self, validated_data: dict[str, Any]) -> PactUser:
        """Create and persist a new PactUser instance."""
        return PactUser.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
        )


class UserProfileSerializer(serializers.ModelSerializer):
    """Read-only serializer representing user profile information."""

    class Meta:
        """Serializer metadata and field definitions."""

        model = PactUser
        fields = ["id", "email", "is_active", "created_at"]
        read_only_fields = fields
