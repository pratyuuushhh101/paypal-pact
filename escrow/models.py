"""Domain models for outcome-based escrow agreements and ledger audit logs."""

from decimal import Decimal
from typing import Any
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class Pact(models.Model):
    """Represents a financial agreement between a buyer and a seller held in escrow."""

    class State(models.TextChoices):
        """Lifecycle states of an escrow pact."""

        DRAFT = "DRAFT", _("Draft")
        AUTHORIZED = "AUTHORIZED", _("Authorized")
        SUBMITTED = "SUBMITTED", _("Submitted")
        IN_REVIEW = "IN_REVIEW", _("In Review")
        CAPTURED = "CAPTURED", _("Captured")
        VOIDED = "VOIDED", _("Voided")
        REJECTED = "REJECTED", _("Rejected")
        REVISION_REQUESTED = "REVISION_REQUESTED", _("Revision Requested")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the pact."),
    )
    state = models.CharField(
        max_length=32,
        choices=State.choices,
        default=State.DRAFT,
        db_index=True,
        help_text=_("Current lifecycle state of the escrow pact."),
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="buyer_pacts",
        help_text=_("User initiating and funding the escrow pact."),
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="seller_pacts",
        null=True,
        blank=True,
        help_text=_("User delivering the work. Can be unassigned during draft phases."),
    )
    deliverable_type = models.CharField(
        max_length=64,
        default="JSON_DATASET",
        help_text=_("Contracted output specification (e.g., JSON_DATASET)."),
    )
    deliverable_payload = models.JSONField(
        null=True,
        blank=True,
        help_text=_("Submitted deliverable dataset or payload awaiting verification."),
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Total amount to be captured or voided upon outcome verification."),
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text=_("Three-letter ISO 4217 currency code."),
    )

    # PayPal API Tracking
    paypal_order_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("PayPal Order ID associated with authorization intent."),
    )
    paypal_authorization_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("PayPal Authorization ID reserved for funds capture."),
    )

    # Audit Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text=_("Timestamp when the pact was created."),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_("Timestamp when the pact was last updated."),
    )

    # Retry / revision loop tracking
    max_attempts = models.PositiveSmallIntegerField(
        default=3,
        help_text=_("Maximum allowed submission attempts before voiding."),
    )
    current_attempt = models.PositiveSmallIntegerField(
        default=1,
        help_text=_("Current submission attempt index."),
    )
    last_rejection_reason = models.TextField(
        blank=True,
        null=True,
        help_text=_("AI rationale for previous revision request."),
    )
    last_rejection_flags = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Security or quality flags from previous attempt."),
    )

    class Meta:
        verbose_name = _("Pact")
        verbose_name_plural = _("Pacts")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["state", "created_at"], name="idx_pact_state_created"),
            models.Index(fields=["buyer", "state"], name="idx_pact_buyer_state"),
            models.Index(fields=["seller", "state"], name="idx_pact_seller_state"),
        ]

    def __str__(self) -> str:
        """Return a descriptive string representation of the pact."""
        seller_ident: str = str(self.seller) if self.seller else "Unassigned"
        return f"Pact {self.id} [{self.state}] - {self.amount} {self.currency} (Buyer: {self.buyer}, Seller: {seller_ident})"


class PactLedger(models.Model):
    """Immutable, append-only audit log capturing state transitions and execution events."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for this ledger log entry."),
    )
    pact = models.ForeignKey(
        Pact,
        on_delete=models.CASCADE,
        related_name="ledger_entries",
        help_text=_("Associated pact record."),
    )
    action = models.CharField(
        max_length=64,
        db_index=True,
        help_text=_("Action performed (e.g., STATE_CHANGED, VERIFICATION_FAILED)."),
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Arbitrary structured metadata snapshot capturing event context."),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        editable=False,
        help_text=_("Immutable timestamp of when the event occurred."),
    )

    class Meta:
        verbose_name = _("Pact Ledger Entry")
        verbose_name_plural = _("Pact Ledger Entries")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["pact", "created_at"], name="idx_ledger_pact_created"),
            models.Index(fields=["action", "created_at"], name="idx_ledger_action_created"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Prevent updates to ensure append-only immutability."""
        if not self._state.adding:
            raise ValidationError(
                _("Ledger records are immutable and cannot be updated once created.")
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Prevent individual deletion to preserve audit integrity."""
        raise ValidationError(_("Ledger records cannot be deleted directly."))

    def __str__(self) -> str:
        """Return a string summary of the ledger entry."""
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] Pact {self.pact_id} - {self.action}"
