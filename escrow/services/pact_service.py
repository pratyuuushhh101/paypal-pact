"""Business logic service layer for escrow pact lifecycles."""

from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction

from escrow.models import Pact, PactLedger
from escrow.services.paypal_service import PayPalAPIException, PayPalService
from escrow.tasks import verify_pact_deliverable

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)


class PactService:
    """Service encapsulating transactional business logic and state machine transitions for Pacts."""

    def __init__(self, paypal_service: PayPalService | None = None) -> None:
        """Initialize service with an optional injected PayPalService instance."""
        self.paypal_service: PayPalService = paypal_service or PayPalService()

    @transaction.atomic
    def create_draft_pact(
        self,
        buyer: Any,
        amount: Decimal,
        currency: str = "USD",
        deliverable_type: str = "JSON_DATASET",
        seller: Any | None = None,
        quality_rubric: str = "",
        confidence_threshold: Decimal = Decimal("0.85"),
    ) -> tuple[Pact, str]:
        """Create a new Pact in DRAFT state, initiate PayPal authorization order, and record audit log.

        Args:
            buyer: The user initiating the contract.
            amount: Funding amount to be held in escrow.
            currency: Three-letter ISO currency code.
            deliverable_type: Deliverable specification identifier.
            seller: Optional seller user instance.
            quality_rubric: Optional buyer acceptance criteria for verification.
            confidence_threshold: Minimum AI confidence required for fund capture.

        Returns:
            Tuple of (Pact instance, PayPal buyer approval URL).

        Raises:
            PayPalAPIException: If PayPal order creation fails or approval link is missing.
        """
        pact: Pact = Pact.objects.create(
            buyer=buyer,
            seller=seller,
            amount=amount,
            currency=currency,
            deliverable_type=deliverable_type,
            quality_rubric=quality_rubric,
            confidence_threshold=confidence_threshold,
            state=Pact.State.DRAFT,
        )

        logger.info("Created local draft Pact %s. Contacting PayPal to initiate authorization order.", pact.id)

        try:
            order_data: dict[str, Any] = self.paypal_service.create_authorization_order(pact)
        except PayPalAPIException as exc:
            logger.error("Failed to generate PayPal order for Pact %s: %s", pact.id, exc)
            raise

        order_id: str | None = order_data.get("id")
        if not order_id:
            raise PayPalAPIException("PayPal response did not contain an order ID.")

        # Extract buyer approval redirect URL
        approve_url: str | None = None
        for link in order_data.get("links", []):
            if link.get("rel") == "approve":
                approve_url = link.get("href")
                break

        if not approve_url:
            raise PayPalAPIException(
                "PayPal order response did not contain a valid buyer approval link.",
                response_data=order_data,
            )

        pact.paypal_order_id = order_id
        pact.save(update_fields=["paypal_order_id", "updated_at"])

        PactLedger.objects.create(
            pact=pact,
            action="PACT_CREATED",
            details={
                "paypal_order_id": order_id,
                "amount": str(amount),
                "currency": currency,
                "deliverable_type": deliverable_type,
                "approve_url": approve_url,
                "quality_rubric": quality_rubric,
                "confidence_threshold": str(confidence_threshold),
            },
        )

        logger.info("Pact %s successfully linked to PayPal order %s with approve URL.", pact.id, order_id)
        return pact, approve_url

    @transaction.atomic
    def confirm_pact_authorization(self, pact: Pact, order_id: str) -> Pact:
        """Confirm PayPal authorization for an approved order and transition Pact state to AUTHORIZED.

        Args:
            pact: The Pact instance to be confirmed.
            order_id: The PayPal order ID approved by the buyer.

        Returns:
            Updated Pact instance in AUTHORIZED state.

        Raises:
            ValueError: If pact state is invalid or order_id does not match.
            PayPalAPIException: If PayPal authorization call fails or authorization ID is absent.
        """
        if pact.state != Pact.State.DRAFT:
            raise ValueError(f"Cannot authorize Pact {pact.id} from current state '{pact.state}'. Expected DRAFT.")

        if pact.paypal_order_id and pact.paypal_order_id != order_id:
            raise ValueError(
                f"Order ID mismatch: Provided '{order_id}' does not match Pact record '{pact.paypal_order_id}'."
            )

        logger.info("Executing PayPal authorization for Pact %s (Order: %s)", pact.id, order_id)

        auth_data: dict[str, Any] = self.paypal_service.authorize_order(order_id)

        # Extract authorization ID from PayPal response payload
        authorization_id: str | None = self._extract_authorization_id(auth_data)
        if not authorization_id:
            raise PayPalAPIException(
                message="PayPal authorization succeeded but no authorization ID was returned.",
                response_data=auth_data,
            )

        pact.paypal_authorization_id = authorization_id
        pact.state = Pact.State.AUTHORIZED
        pact.save(update_fields=["paypal_authorization_id", "state", "updated_at"])

        PactLedger.objects.create(
            pact=pact,
            action="AUTHORIZED",
            details={
                "paypal_order_id": order_id,
                "paypal_authorization_id": authorization_id,
                "paypal_status": auth_data.get("status"),
            },
        )

        logger.info("Pact %s successfully transitioned to AUTHORIZED (Auth ID: %s)", pact.id, authorization_id)
        return pact

    @transaction.atomic
    def submit_pact_deliverable(self, pact: Pact, payload: dict[str, Any]) -> Pact:
        """Submit seller deliverable payload and queue asynchronous verification.

        Accepts submissions from both AUTHORIZED state (first attempt) and
        REVISION_REQUESTED state (subsequent resubmission attempts). The
        current_attempt counter is incremented on every resubmission.

        Args:
            pact: The target Pact instance.
            payload: Deliverable dataset or data dictionary submitted by the seller.

        Returns:
            Updated Pact instance in SUBMITTED state.

        Raises:
            ValueError: If pact is not in AUTHORIZED or REVISION_REQUESTED state,
                        or if the payload is empty.
        """
        allowed_states: tuple[str, ...] = (
            Pact.State.AUTHORIZED,
            Pact.State.REVISION_REQUESTED,
        )
        if pact.state not in allowed_states:
            raise ValueError(
                f"Cannot submit deliverable for Pact {pact.id} from state '{pact.state}'. "
                f"Pact must be in AUTHORIZED state or REVISION_REQUESTED state."
            )

        if not payload:
            raise ValueError("Deliverable payload cannot be empty.")

        is_resubmission: bool = pact.state == Pact.State.REVISION_REQUESTED
        if is_resubmission:
            pact.current_attempt += 1
            logger.info(
                "Resubmission detected for Pact %s. Incrementing attempt to %d/%d.",
                pact.id,
                pact.current_attempt,
                pact.max_attempts,
            )

        pact.deliverable_payload = payload
        pact.state = Pact.State.SUBMITTED

        update_fields: list[str] = ["deliverable_payload", "state", "updated_at"]
        if is_resubmission:
            update_fields.append("current_attempt")

        pact.save(update_fields=update_fields)

        action: str = "DELIVERABLE_RESUBMITTED" if is_resubmission else "DELIVERABLE_SUBMITTED"
        PactLedger.objects.create(
            pact=pact,
            action=action,
            details={
                "deliverable_type": pact.deliverable_type,
                "payload_keys": list(payload.keys()) if isinstance(payload, dict) else [],
                "attempt": pact.current_attempt,
                "max_attempts": pact.max_attempts,
            },
        )

        logger.info(
            "Deliverable %s for Pact %s (attempt %d/%d). Enqueuing Celery verification task.",
            "resubmitted" if is_resubmission else "submitted",
            pact.id,
            pact.current_attempt,
            pact.max_attempts,
        )

        # Enqueue verification task upon transaction commit to prevent DB read race conditions
        transaction.on_commit(lambda: verify_pact_deliverable.delay(str(pact.id)))

        return pact

    @staticmethod
    def _extract_authorization_id(auth_payload: dict[str, Any]) -> str | None:
        """Traverse PayPal order authorization payload to extract authorization ID."""
        purchase_units: list[dict[str, Any]] = auth_payload.get("purchase_units", [])
        if purchase_units:
            payments: dict[str, Any] = purchase_units[0].get("payments", {})
            authorizations: list[dict[str, Any]] = payments.get("authorizations", [])
            if authorizations:
                return authorizations[0].get("id")

        # Fallback to direct authorization ID or custom payload shapes
        if "id" in auth_payload and auth_payload.get("status") in ("CREATED", "COMPLETED", "PENDING"):
            return auth_payload.get("id")

        return None
