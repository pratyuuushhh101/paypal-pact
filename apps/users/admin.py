"""Admin interface configuration for custom user model."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import PactUser


@admin.register(PactUser)
class PactUserAdmin(BaseUserAdmin):
    """Admin configuration for PactUser."""

    list_display = ("email", "is_staff", "is_active", "created_at")
    list_filter = ("is_staff", "is_active")
    ordering = ("-created_at",)
    search_fields = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "created_at")}),
    )
    readonly_fields = ("created_at", "last_login")
