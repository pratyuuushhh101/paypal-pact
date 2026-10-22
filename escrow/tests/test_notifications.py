"""Unit and integration tests for transactional escrow email notifications."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

from escrow.models import Pact
from escrow.services.ai_service import EvaluationReport
from escrow.services.notification_service import NotificationService, notification_service
from escrow.services.pact_service import PactService
from escrow.tasks import (
    _capture_pact,
    _request_revision,
    _void_pact,
    verify_pact_deliverable,
)

User = get_user_model()


class NotificationServiceTests(TestCase):
    """Test suite verifying transactional notification emails and template rendering."""

    def setUp(self) -> None:
        """Create test users and baseline pact fixture."""
        mail.outbox.clear()
        self.buyer = User.objects.create_user(email="buyer_notify@example.com", password="password123")
        self.seller = User.objects.create_user(email="seller_notify@example.com", password="password123")
        self.pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("250.00"),
            currency="USD",
            deliverable_type="JSON_DATASET",
            current_attempt=1,
            max_attempts=3,
            state=Pact.State.AUTHORIZED,
            paypal_authorization_id="AUTH-NOTIFY-123",
        )
        self.service = NotificationService()

    def test_send_authorization_notice_delivers_to_buyer(self) -> None:
        """Verify authorization notification emails buyer with escrow hold details."""
        success = self.service.send_authorization_notice(self.pact)
        self.assertTrue(success)

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, f"[Pact Escrow] Funds Authorized - Pact #{self.pact.id}")
        self.assertEqual(sent_email.to, ["buyer_notify@example.com"])
        self.assertIn("250.00 USD", sent_email.body)
        self.assertIn("JSON_DATASET", sent_email.body)
        self.assertIn("AUTHORIZED", sent_email.body)

    def test_send_authorization_notice_missing_buyer_fails_gracefully(self) -> None:
        """Verify missing buyer email logs warning and returns False without raising."""
        self.pact.buyer = None
        success = self.service.send_authorization_notice(self.pact)
        self.assertFalse(success)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_submission_notice_delivers_to_buyer(self) -> None:
        """Verify deliverable submission notice sends attempt info to buyer."""
        self.pact.current_attempt = 2
        success = self.service.send_submission_notice(self.pact)
        self.assertTrue(success)

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, f"[Pact Escrow] Deliverable Submitted - Pact #{self.pact.id}")
        self.assertEqual(sent_email.to, ["buyer_notify@example.com"])
        self.assertIn("2 of 3", sent_email.body)
        self.assertIn("JSON_DATASET", sent_email.body)

    def test_send_revision_requested_notice_delivers_to_seller(self) -> None:
        """Verify revision request emails seller with reason, flags, and remaining retries."""
        self.pact.last_rejection_flags = ["low_quality", "missing_keys"]
        self.pact.save()

        success = self.service.send_revision_requested_notice(
            pact=self.pact,
            reason="Payload contains empty email values in 4 records.",
            attempt=1,
        )
        self.assertTrue(success)

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(
            sent_email.subject,
            f"[Pact Escrow] Revision Requested - Pact #{self.pact.id} (Attempt 1 of 3)",
        )
        self.assertEqual(sent_email.to, ["seller_notify@example.com"])
        self.assertIn("Payload contains empty email values", sent_email.body)
        self.assertIn("low_quality, missing_keys", sent_email.body)
        self.assertIn("Remaining Attempts: 2", sent_email.body)

    def test_send_revision_requested_notice_unassigned_seller_fails_gracefully(self) -> None:
        """Verify revision request without assigned seller returns False cleanly."""
        self.pact.seller = None
        success = self.service.send_revision_requested_notice(
            pact=self.pact,
            reason="Sample error",
            attempt=1,
        )
        self.assertFalse(success)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_resolution_notice_captured_notifies_both_parties(self) -> None:
        """Verify CAPTURED state delivers completion notice to buyer and payment notice to seller."""
        self.pact.state = Pact.State.CAPTURED
        success = self.service.send_resolution_notice(
            pact=self.pact,
            state="CAPTURED",
            reason="All 500 records verified successfully with confidence 0.98.",
        )
        self.assertTrue(success)

        # Buyer notification + Seller notification
        self.assertEqual(len(mail.outbox), 2)
        recipients = [m.to[0] for m in mail.outbox]
        self.assertIn("buyer_notify@example.com", recipients)
        self.assertIn("seller_notify@example.com", recipients)

        buyer_mail = next(m for m in mail.outbox if "buyer_notify@example.com" in m.to)
        self.assertEqual(
            buyer_mail.subject,
            f"[Pact Escrow] Contract Completed & Funds Released - Pact #{self.pact.id}",
        )
        self.assertIn("All 500 records verified successfully", buyer_mail.body)

        seller_mail = next(m for m in mail.outbox if "seller_notify@example.com" in m.to)
        self.assertEqual(
            seller_mail.subject,
            f"[Pact Escrow] Payment Released! - Pact #{self.pact.id}",
        )
        self.assertIn("250.00 USD", seller_mail.body)

    def test_send_resolution_notice_voided_notifies_buyer_of_refund(self) -> None:
        """Verify VOIDED state notifies buyer of released hold and refund."""
        self.pact.state = Pact.State.VOIDED
        success = self.service.send_resolution_notice(
            pact=self.pact,
            state="VOIDED",
            reason="Max revision attempts exceeded.",
        )
        self.assertTrue(success)

        buyer_mail = next(m for m in mail.outbox if "buyer_notify@example.com" in m.to)
        self.assertEqual(
            buyer_mail.subject,
            f"[Pact Escrow] Escrow Hold Voided & Refunded - Pact #{self.pact.id}",
        )
        self.assertIn("Max revision attempts exceeded", buyer_mail.body)
        self.assertIn("250.00 USD", buyer_mail.body)

    @patch("escrow.services.notification_service.send_mail", side_effect=RuntimeError("SMTP Outage"))
    def test_send_email_handles_exceptions_without_crashing(self, mock_send_mail: MagicMock) -> None:
        """Verify email dispatch failures are logged and handled fail-safe."""
        success = self.service.send_authorization_notice(self.pact)
        self.assertFalse(success)


class LifecycleNotificationTriggerTests(TestCase):
    """Integration test suite verifying notification hooks into pact service and celery tasks."""

    def setUp(self) -> None:
        """Set up users, fixtures, and clean outbox."""
        mail.outbox.clear()
        self.buyer = User.objects.create_user(email="lifecycle_buyer@example.com", password="password123")
        self.seller = User.objects.create_user(email="lifecycle_seller@example.com", password="password123")
        self.pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("180.00"),
            currency="USD",
            deliverable_type="JSON_DATASET",
            state=Pact.State.DRAFT,
            paypal_order_id="ORDER-LIFE-1",
        )

    @patch("escrow.services.paypal_service.PayPalService.authorize_order")
    def test_confirm_pact_authorization_triggers_notice(self, mock_authorize: MagicMock) -> None:
        """Verify confirm_pact_authorization sends authorization email to buyer."""
        mock_authorize.return_value = {
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"authorizations": [{"id": "AUTH-LIFE-99"}]}}],
        }

        pact_service = PactService()
        pact_service.confirm_pact_authorization(self.pact, "ORDER-LIFE-1")

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ["lifecycle_buyer@example.com"])
        self.assertIn("Funds Authorized", sent_email.subject)

    @patch("escrow.tasks.verify_pact_deliverable.delay")
    def test_submit_pact_deliverable_triggers_notice(self, mock_delay: MagicMock) -> None:
        """Verify submit_pact_deliverable sends submission notice to buyer."""
        self.pact.state = Pact.State.AUTHORIZED
        self.pact.save()

        pact_service = PactService()
        pact_service.submit_pact_deliverable(self.pact, [{"id": 1, "data": "test"}])

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ["lifecycle_buyer@example.com"])
        self.assertIn("Deliverable Submitted", sent_email.subject)

    def test_request_revision_helper_triggers_notice(self) -> None:
        """Verify _request_revision helper in tasks.py sends email notice to seller."""
        self.pact.state = Pact.State.SUBMITTED
        self.pact.save()

        _request_revision(self.pact, reason="Dataset failed schema check", flags=["invalid_format"])

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ["lifecycle_seller@example.com"])
        self.assertIn("Revision Requested", sent_email.subject)
        self.assertIn("Dataset failed schema check", sent_email.body)

    @patch("escrow.services.paypal_service.PayPalService.capture_authorization")
    def test_capture_pact_helper_triggers_notice(self, mock_capture: MagicMock) -> None:
        """Verify _capture_pact helper in tasks.py sends resolution emails."""
        mock_capture.return_value = {"id": "CAPTURE-LIFE-1", "status": "COMPLETED"}
        self.pact.state = Pact.State.SUBMITTED
        self.pact.paypal_authorization_id = "AUTH-LIFE-1"
        self.pact.save()

        mock_paypal = MagicMock()
        mock_paypal.capture_authorization.return_value = {"id": "CAPTURE-LIFE-1", "status": "COMPLETED"}

        _capture_pact(self.pact, ai_reasoning="Flawless dataset", paypal_service=mock_paypal)

        # Buyer + Seller resolution notices
        self.assertEqual(len(mail.outbox), 2)
        recipients = [m.to[0] for m in mail.outbox]
        self.assertIn("lifecycle_buyer@example.com", recipients)
        self.assertIn("lifecycle_seller@example.com", recipients)

    @patch("escrow.services.paypal_service.PayPalService.void_authorization")
    def test_void_pact_helper_triggers_notice(self, mock_void: MagicMock) -> None:
        """Verify _void_pact helper in tasks.py sends resolution refund email to buyer."""
        self.pact.state = Pact.State.SUBMITTED
        self.pact.paypal_authorization_id = "AUTH-LIFE-1"
        self.pact.save()

        mock_paypal = MagicMock()
        _void_pact(self.pact, reason="Confidence score 0.40 below floor", paypal_service=mock_paypal)

        buyer_mail = next(m for m in mail.outbox if "lifecycle_buyer@example.com" in m.to)
        self.assertIn("Escrow Hold Voided & Refunded", buyer_mail.subject)
        self.assertIn("Confidence score 0.40 below floor", buyer_mail.body)


class CeleryTaskEmailFailureResilienceTests(TestCase):
    """Verify that Celery verification tasks do NOT fail or crash when email delivery encounters errors."""

    def setUp(self) -> None:
        """Set up test users and submitted pact fixture."""
        mail.outbox.clear()
        self.buyer = User.objects.create_user(email="celery_buyer@example.com", password="password123")
        self.seller = User.objects.create_user(email="celery_seller@example.com", password="password123")
        self.pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("300.00"),
            currency="USD",
            deliverable_type="JSON_DATASET",
            current_attempt=1,
            max_attempts=3,
            state=Pact.State.SUBMITTED,
            paypal_authorization_id="AUTH-CELERY-HOLD",
            deliverable_payload=[
                {"id": 1, "name": "Customer 1"},
                {"id": 2, "name": "Customer 2"},
            ],
        )

    @patch("escrow.services.paypal_service.PayPalService.capture_authorization")
    @patch("escrow.services.ai_service.GroqVerifier.evaluate_payload")
    @patch("escrow.services.notification_service.send_mail", side_effect=RuntimeError("SMTP Connection Refused"))
    def test_celery_task_captures_funds_when_email_fails(
        self,
        mock_send_mail: MagicMock,
        mock_evaluate: MagicMock,
        mock_capture: MagicMock,
    ) -> None:
        """Verify verify_pact_deliverable succeeds and captures funds even if email throws an error."""
        mock_evaluate.return_value = EvaluationReport(
            passed=True,
            confidence_score=0.96,
            reasoning="Valid deliverable payload.",
            flags=[],
        )
        mock_capture.return_value = {"id": "CAPTURE-CELERY-OK", "status": "COMPLETED"}

        # Execute Celery task directly
        verify_pact_deliverable(str(self.pact.id))

        self.pact.refresh_from_db()
        self.assertEqual(self.pact.state, Pact.State.CAPTURED)
        mock_capture.assert_called_once()
        mock_send_mail.assert_called()

    @patch("escrow.services.ai_service.GroqVerifier.evaluate_payload")
    @patch("escrow.services.notification_service.send_mail", side_effect=Exception("Mailgun API Error"))
    def test_celery_task_requests_revision_when_email_fails(
        self,
        mock_send_mail: MagicMock,
        mock_evaluate: MagicMock,
    ) -> None:
        """Verify verify_pact_deliverable sets REVISION_REQUESTED state even if email fails."""
        mock_evaluate.return_value = EvaluationReport(
            passed=False,
            confidence_score=0.60,
            reasoning="Missing required contact fields.",
            flags=["low_quality"],
        )

        verify_pact_deliverable(str(self.pact.id))

        self.pact.refresh_from_db()
        self.assertEqual(self.pact.state, Pact.State.REVISION_REQUESTED)
        self.assertEqual(self.pact.last_rejection_reason, "Missing required contact fields.")
        mock_send_mail.assert_called()

    @patch("escrow.services.paypal_service.PayPalService.void_authorization")
    @patch("escrow.services.ai_service.GroqVerifier.evaluate_payload")
    @patch("escrow.services.notification_service.send_mail", side_effect=TimeoutError("SMTP Outage Timeout"))
    def test_celery_task_voids_pact_when_email_fails(
        self,
        mock_send_mail: MagicMock,
        mock_evaluate: MagicMock,
        mock_void: MagicMock,
    ) -> None:
        """Verify verify_pact_deliverable voids pact when retry attempts exhausted even if email fails."""
        self.pact.current_attempt = 3
        self.pact.max_attempts = 3
        self.pact.save()

        mock_evaluate.return_value = EvaluationReport(
            passed=False,
            confidence_score=0.45,
            reasoning="Exhausted final attempt with bad data.",
            flags=["low_quality"],
        )
        mock_void.return_value = {"status": "VOIDED"}

        verify_pact_deliverable(str(self.pact.id))

        self.pact.refresh_from_db()
        self.assertEqual(self.pact.state, Pact.State.VOIDED)
        mock_void.assert_called_once()
        mock_send_mail.assert_called()
