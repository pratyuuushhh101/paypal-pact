"""Asynchronous Celery tasks for escrow verification and background processing."""

import logging
from typing import Any

from celery import shared_task
from django.db import transaction

from escrow.services.ai_service import AIVerificationException, EvaluationReport, GroqVerifier

logger = logging.getLogger(__name__)


@shared_task(
    name="escrow.tasks.verify_pact_deliverable",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def verify_pact_deliverable(self, pact_id: str) -> None:
    """Execute deterministic and Groq AI verification on a submitted pact deliverable.

    Pipeline stages:
        1. Transition pact to IN_REVIEW and log the event.
        2. Deterministic check — validate payload shape (list of dicts, >= 2 items).
        3. Semantic check — Groq AI structured evaluation (checks prompt injections & quality).
        4. Resolution — CAPTURE funds if passed and confidence >= 0.85, VOID or REJECT otherwise.

    Args:
        pact_id: String UUID of the Pact awaiting verification.
    """
    from escrow.models import Pact, PactLedger
    from escrow.services.paypal_service import PayPalAPIException, PayPalService

    logger.info("Starting verification pipeline for Pact %s", pact_id)

    # ------------------------------------------------------------------
    # Stage 0: Fetch the Pact
    # ------------------------------------------------------------------
    try:
        pact: Pact = Pact.objects.get(id=pact_id)
    except Pact.DoesNotExist:
        logger.error("Pact %s not found. Aborting verification task.", pact_id)
        return

    if pact.state != Pact.State.SUBMITTED:
        logger.warning(
            "Pact %s is in state '%s', expected SUBMITTED. Aborting verification.",
            pact_id,
            pact.state,
        )
        return
    # ------------------------------------------------------------------
    # Stage 1: Transition to IN_REVIEW
    # ------------------------------------------------------------------
    with transaction.atomic():
        pact.state = Pact.State.IN_REVIEW
        pact.save(update_fields=["state", "updated_at"])

        PactLedger.objects.create(
            pact=pact,
            action="REVIEW_STARTED",
            details={"previous_state": Pact.State.SUBMITTED},
        )

    logger.info("Pact %s transitioned to IN_REVIEW.", pact_id)

    paypal_service: PayPalService = PayPalService()
    payload: Any = pact.deliverable_payload

    # ------------------------------------------------------------------
    # Stage 2: Deterministic Check
    # ------------------------------------------------------------------
    deterministic_passed: bool = True
    deterministic_reason: str = ""

    if not isinstance(payload, list):
        deterministic_passed = False
        deterministic_reason = (
            f"Payload must be a list of dictionaries. Received type: {type(payload).__name__}."
        )
    elif len(payload) < 2:
        deterministic_passed = False
        deterministic_reason = (
            f"Payload must contain at least 2 items. Received {len(payload)} item(s)."
        )
    elif not all(isinstance(item, dict) for item in payload):
        deterministic_passed = False
        non_dict_types = {type(item).__name__ for item in payload if not isinstance(item, dict)}
        deterministic_reason = (
            f"All payload items must be dictionaries. Found non-dict types: {non_dict_types}."
        )

    if not deterministic_passed:
        logger.warning(
            "Deterministic check FAILED for Pact %s: %s", pact_id, deterministic_reason,
        )
        if pact.current_attempt < pact.max_attempts:
            logger.info(
                "Pact %s has %d attempt(s) remaining. Requesting revision instead of rejecting.",
                pact_id,
                pact.max_attempts - pact.current_attempt,
            )
            _request_revision(
                pact=pact,
                reason=deterministic_reason,
                flags=["DETERMINISTIC_FAILURE"],
            )
        else:
            logger.warning(
                "Pact %s exhausted all %d attempt(s) on deterministic check. Rejecting and voiding.",
                pact_id,
                pact.max_attempts,
            )
            _reject_pact(pact, deterministic_reason, paypal_service)
        return

    logger.info("Deterministic check PASSED for Pact %s.", pact_id)

    # ------------------------------------------------------------------
    # Stage 3: Semantic Check via Groq
    # ------------------------------------------------------------------
    verifier: GroqVerifier = GroqVerifier()
    try:
        report: EvaluationReport = verifier.evaluate_payload(payload)
    except AIVerificationException as exc:
        logger.exception("AI evaluation error for Pact %s: %s", pact_id, exc)
        PactLedger.objects.create(
            pact=pact,
            action="AI_SERVICE_ERROR",
            details={"error": str(exc)},
        )
        return

    logger.info(
        "Groq evaluation result for Pact %s: passed=%s, confidence=%.2f, flags=%s",
        pact_id,
        report.passed,
        report.confidence_score,
        report.flags,
    )

    # ------------------------------------------------------------------
    # Stage 4: Resolution State Machine
    # ------------------------------------------------------------------
    # If report.passed is True AND report.confidence_score >= 0.85, proceed to _capture_pact.
    # Otherwise, pass report.reasoning to _void_pact to release the funds.
    if report.passed and report.confidence_score >= 0.85:
        logger.info(
            "Pact %s PASSED AI verification (confidence: %.2f >= 0.85). Capturing funds.",
            pact_id,
            report.confidence_score,
        )
        _capture_pact(
            pact=pact,
            ai_reasoning=report.reasoning,
            paypal_service=paypal_service,
            confidence_score=report.confidence_score,
            flags=report.flags,
        )
    else:
        void_reason: str = report.reasoning
        if report.passed and report.confidence_score < 0.85:
            void_reason = (
                f"Evaluation passed but confidence score ({report.confidence_score:.2f}) "
                f"did not meet the minimum threshold (0.85). {report.reasoning}"
            )
        logger.warning(
            "Pact %s FAILED verification threshold (passed=%s, confidence=%.2f). Checking retry budget: %s",
            pact_id,
            report.passed,
            report.confidence_score,
            void_reason,
        )
        if pact.current_attempt < pact.max_attempts:
            logger.info(
                "Pact %s has %d attempt(s) remaining. Requesting revision (hold preserved).",
                pact_id,
                pact.max_attempts - pact.current_attempt,
            )
            _request_revision(
                pact=pact,
                reason=void_reason,
                flags=report.flags,
            )
        else:
            logger.warning(
                "Pact %s exhausted all %d attempt(s). Voiding PayPal hold.",
                pact_id,
                pact.max_attempts,
            )
            _void_pact(
                pact=pact,
                reason=void_reason,
                paypal_service=paypal_service,
                confidence_score=report.confidence_score,
                flags=report.flags,
            )


def _request_revision(
    pact: "Pact",
    reason: str,
    flags: list[str] | None = None,
) -> None:
    """Transition a pact to REVISION_REQUESTED without voiding the PayPal authorization hold.

    Called when the deliverable fails verification but the seller still has
    remaining submission attempts (``current_attempt < max_attempts``).
    The PayPal authorization hold is intentionally preserved so funds remain
    escrowed for the next attempt.

    Args:
        pact: The Pact instance to transition.
        reason: Human-readable rationale for the revision request.
        flags: Optional list of security or quality tags identified during verification.
    """
    from escrow.models import Pact, PactLedger

    with transaction.atomic():
        pact.state = Pact.State.REVISION_REQUESTED
        pact.last_rejection_reason = reason
        pact.last_rejection_flags = flags or []
        pact.save(update_fields=[
            "state",
            "last_rejection_reason",
            "last_rejection_flags",
            "updated_at",
        ])

        PactLedger.objects.create(
            pact=pact,
            action="REVISION_REQUESTED",
            details={
                "reason": reason,
                "flags": flags or [],
                "attempt": pact.current_attempt,
                "max_attempts": pact.max_attempts,
                "attempts_remaining": pact.max_attempts - pact.current_attempt,
            },
        )

    logger.info(
        "Pact %s transitioned to REVISION_REQUESTED (attempt %d/%d). PayPal hold preserved.",
        pact.id,
        pact.current_attempt,
        pact.max_attempts,
    )


def _reject_pact(
    pact: "Pact",
    reason: str,
    paypal_service: "PayPalService",
) -> None:
    """Reject a pact that fails deterministic validation and void the authorization hold.

    Args:
        pact: The Pact instance to reject.
        reason: Human-readable rejection rationale.
        paypal_service: PayPalService instance for voiding.
    """
    from escrow.models import Pact, PactLedger
    from escrow.services.paypal_service import PayPalAPIException

    with transaction.atomic():
        pact.state = Pact.State.REJECTED
        pact.save(update_fields=["state", "updated_at"])

        PactLedger.objects.create(
            pact=pact,
            action="VERIFICATION_FAILED",
            details={
                "check_type": "DETERMINISTIC",
                "reason": reason,
                "resolution": "REJECTED",
            },
        )

    logger.info("Pact %s REJECTED. Attempting to void PayPal authorization.", pact.id)

    if pact.paypal_authorization_id:
        try:
            paypal_service.void_authorization(pact.paypal_authorization_id)
            PactLedger.objects.create(
                pact=pact,
                action="FUNDS_VOIDED",
                details={
                    "paypal_authorization_id": pact.paypal_authorization_id,
                    "trigger": "DETERMINISTIC_REJECTION",
                },
            )
            logger.info(
                "PayPal authorization %s voided for rejected Pact %s.",
                pact.paypal_authorization_id,
                pact.id,
            )
        except PayPalAPIException as exc:
            logger.exception(
                "Failed to void PayPal authorization %s for Pact %s: %s",
                pact.paypal_authorization_id,
                pact.id,
                exc,
            )
            PactLedger.objects.create(
                pact=pact,
                action="VOID_FAILED",
                details={
                    "paypal_authorization_id": pact.paypal_authorization_id,
                    "error": str(exc),
                    "status_code": getattr(exc, "status_code", None),
                },
            )


def _void_pact(
    pact: "Pact",
    reason: str,
    paypal_service: "PayPalService",
    confidence_score: float | None = None,
    flags: list[str] | None = None,
) -> None:
    """Void a pact that fails semantic AI verification and release the escrow hold.

    Args:
        pact: The Pact instance to void.
        reason: AI reasoning string explaining the failure.
        paypal_service: PayPalService instance for voiding.
        confidence_score: Optional AI confidence score.
        flags: Optional identified security/quality tags.
    """
    from escrow.models import Pact, PactLedger
    from escrow.services.paypal_service import PayPalAPIException

    with transaction.atomic():
        pact.state = Pact.State.VOIDED
        pact.save(update_fields=["state", "updated_at"])

        PactLedger.objects.create(
            pact=pact,
            action="VERIFICATION_FAILED",
            details={
                "check_type": "SEMANTIC",
                "ai_reasoning": reason,
                "confidence_score": confidence_score,
                "flags": flags or [],
                "resolution": "VOIDED",
            },
        )

    logger.info("Pact %s VOIDED due to semantic failure. Releasing PayPal hold.", pact.id)

    if pact.paypal_authorization_id:
        try:
            paypal_service.void_authorization(pact.paypal_authorization_id)
            PactLedger.objects.create(
                pact=pact,
                action="FUNDS_VOIDED",
                details={
                    "paypal_authorization_id": pact.paypal_authorization_id,
                    "ai_reasoning": reason,
                    "confidence_score": confidence_score,
                    "flags": flags or [],
                    "trigger": "SEMANTIC_FAILURE",
                },
            )
            logger.info(
                "PayPal authorization %s voided for Pact %s.",
                pact.paypal_authorization_id,
                pact.id,
            )
        except PayPalAPIException as exc:
            logger.exception(
                "Failed to void PayPal authorization %s for Pact %s: %s",
                pact.paypal_authorization_id,
                pact.id,
                exc,
            )
            PactLedger.objects.create(
                pact=pact,
                action="VOID_FAILED",
                details={
                    "paypal_authorization_id": pact.paypal_authorization_id,
                    "error": str(exc),
                    "status_code": getattr(exc, "status_code", None),
                },
            )


def _capture_pact(
    pact: "Pact",
    ai_reasoning: str,
    paypal_service: "PayPalService",
    confidence_score: float | None = None,
    flags: list[str] | None = None,
) -> None:
    """Capture escrow funds after all verification checks pass.

    Args:
        pact: The verified Pact instance.
        ai_reasoning: Semantic analysis summary for the audit record.
        paypal_service: PayPalService instance for capturing.
        confidence_score: Optional AI confidence score.
        flags: Optional identified security/quality tags.
    """
    from escrow.models import Pact, PactLedger
    from escrow.services.paypal_service import PayPalAPIException

    logger.info("All checks passed for Pact %s. Capturing PayPal authorization.", pact.id)

    if not pact.paypal_authorization_id:
        logger.error("Pact %s has no PayPal authorization ID. Cannot capture funds.", pact.id)
        PactLedger.objects.create(
            pact=pact,
            action="CAPTURE_FAILED",
            details={"error": "Missing paypal_authorization_id on verified pact."},
        )
        return

    try:
        capture_data: dict = paypal_service.capture_authorization(pact.paypal_authorization_id)
    except PayPalAPIException as exc:
        logger.exception(
            "Failed to capture PayPal authorization %s for Pact %s: %s",
            pact.paypal_authorization_id,
            pact.id,
            exc,
        )
        PactLedger.objects.create(
            pact=pact,
            action="CAPTURE_FAILED",
            details={
                "paypal_authorization_id": pact.paypal_authorization_id,
                "error": str(exc),
                "status_code": getattr(exc, "status_code", None),
            },
        )
        return

    with transaction.atomic():
        pact.state = Pact.State.CAPTURED
        pact.save(update_fields=["state", "updated_at"])

        PactLedger.objects.create(
            pact=pact,
            action="FUNDS_CAPTURED",
            details={
                "paypal_authorization_id": pact.paypal_authorization_id,
                "paypal_capture_id": capture_data.get("id"),
                "paypal_capture_status": capture_data.get("status"),
                "ai_reasoning": ai_reasoning,
                "confidence_score": confidence_score,
                "flags": flags or [],
            },
        )

    logger.info(
        "Pact %s finalized as CAPTURED. Capture ID: %s",
        pact.id,
        capture_data.get("id"),
    )
