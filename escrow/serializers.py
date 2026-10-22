"""Serializers for escrow domain models and action payloads."""

from decimal import Decimal
from typing import Any
from rest_framework import serializers

from .models import Pact, PactLedger


class PactLedgerSerializer(serializers.ModelSerializer):
    """Read-only serializer for immutable audit ledger entries."""

    class Meta:
        model = PactLedger
        fields = [
            "id",
            "pact",
            "action",
            "details",
            "created_at",
        ]
        read_only_fields = fields


class PactSerializer(serializers.ModelSerializer):
    """Serializer for Pact entities with protected financial and state tracking fields."""

    ledger_entries = PactLedgerSerializer(many=True, read_only=True)
    buyer_email = serializers.EmailField(source="buyer.email", read_only=True)
    seller_email = serializers.EmailField(source="seller.email", read_only=True, allow_null=True)

    class Meta:
        model = Pact
        fields = [
            "id",
            "state",
            "buyer",
            "buyer_email",
            "seller",
            "seller_email",
            "deliverable_type",
            "deliverable_payload",
            "amount",
            "currency",
            "paypal_order_id",
            "paypal_authorization_id",
            "max_attempts",
            "current_attempt",
            "last_rejection_reason",
            "last_rejection_flags",
            "created_at",
            "updated_at",
            "ledger_entries",
        ]
        read_only_fields = [
            "id",
            "state",
            "buyer",
            "deliverable_payload",
            "paypal_order_id",
            "paypal_authorization_id",
            "max_attempts",
            "current_attempt",
            "last_rejection_reason",
            "last_rejection_flags",
            "created_at",
            "updated_at",
            "ledger_entries",
        ]


class CreatePactRequestSerializer(serializers.Serializer):
    """Validation schema for creating an escrow pact draft and PayPal authorization order."""

    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="Escrow funding amount.",
    )
    currency = serializers.CharField(
        max_length=3,
        default="USD",
        required=False,
        help_text="ISO 4217 currency code.",
    )
    deliverable_type = serializers.CharField(
        max_length=64,
        default="JSON_DATASET",
        required=False,
        help_text="Contract deliverable identifier.",
    )
    seller_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Optional ID of the seller user.",
    )

    def validate_currency(self, value: str) -> str:
        """Normalize currency code to uppercase."""
        return value.strip().upper()


class ConfirmAuthorizationRequestSerializer(serializers.Serializer):
    """Validation schema for confirming a buyer-approved PayPal order."""

    pact_id = serializers.UUIDField(help_text="UUID of the Pact awaiting authorization confirmation.")
    paypal_order_id = serializers.CharField(
        max_length=128,
        help_text="PayPal Order ID approved by the buyer.",
    )


class SubmitDeliverableRequestSerializer(serializers.Serializer):
    """Validation schema for seller deliverable submission."""

    payload = serializers.JSONField(help_text="Arbitrary JSON payload or dataset to be verified.")

