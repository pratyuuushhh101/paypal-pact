"""Admin interface configuration for escrow models."""

from django.contrib import admin
from .models import Pact, PactLedger


class PactLedgerInline(admin.TabularInline):
    """Inline view of append-only audit ledger."""

    model = PactLedger
    extra = 0
    can_delete = False
    readonly_fields = ("id", "action", "details", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pact)
class PactAdmin(admin.ModelAdmin):
    """Admin configuration for Pact."""

    list_display = ("id", "state", "buyer", "seller", "amount", "currency", "created_at")
    list_filter = ("state", "currency", "deliverable_type")
    search_fields = ("id", "paypal_order_id", "paypal_authorization_id", "buyer__email", "seller__email")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [PactLedgerInline]


@admin.register(PactLedger)
class PactLedgerAdmin(admin.ModelAdmin):
    """Admin configuration for immutable PactLedger entries."""

    list_display = ("id", "pact", "action", "created_at")
    list_filter = ("action",)
    search_fields = ("pact__id", "action")
    readonly_fields = ("id", "pact", "action", "details", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
