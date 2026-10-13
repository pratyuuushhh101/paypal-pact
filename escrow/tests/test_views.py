"""API integration tests for PactViewSet endpoints using DRF APITestCase."""
from escrow.views import PactViewSet
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from escrow.models import Pact, PactLedger
from escrow.services.paypal_service import PayPalAPIException

User = get_user_model()


class PactViewSetAPITests(APITestCase):
    """Integration test suite for escrow REST API endpoints."""

    def setUp(self) -> None:
        """Create sample buyer, seller, and third-party users for authentication testing."""
        self.buyer = User.objects.create_user(email="buyer_api@example.com", password="password123")
        self.seller = User.objects.create_user(email="seller_api@example.com", password="password123")
        self.stranger = User.objects.create_user(email="stranger_api@example.com", password="password123")

        self.create_pact_url = reverse("pact-create-pact")
        self.confirm_auth_url = reverse("pact-confirm-authorization")

    # -------------------------------------------------------------------------
    # 1. Authentication Enforcement Tests
    # -------------------------------------------------------------------------
    def test_unauthenticated_requests_are_denied(self) -> None:
        """Test endpoints reject unauthenticated access with HTTP 401 Unauthorized."""
        # Unauthenticated create-pact
        resp_create = self.client.post(self.create_pact_url, {"amount": "100.00"})
        self.assertEqual(resp_create.status_code, status.HTTP_401_UNAUTHORIZED)

        # Unauthenticated confirm-authorization
        resp_confirm = self.client.post(
            self.confirm_auth_url,
            {"pact_id": str(uuid.uuid4()), "paypal_order_id": "ORDER-123"},
        )
        self.assertEqual(resp_confirm.status_code, status.HTTP_401_UNAUTHORIZED)

        # Unauthenticated submit-deliverable
        dummy_pact_id = uuid.uuid4()
        submit_url = reverse("pact-submit-deliverable", kwargs={"pk": dummy_pact_id})
        resp_submit = self.client.post(submit_url, {"payload": [{"sample": 1}]})
        self.assertEqual(resp_submit.status_code, status.HTTP_401_UNAUTHORIZED)

    # -------------------------------------------------------------------------
    # 2. POST /api/v1/pacts/create-pact/
    # -------------------------------------------------------------------------
    @patch("escrow.services.pact_service.PayPalService.create_authorization_order")
    def test_create_pact_valid_payload_returns_201_with_approval_url(
        self, mock_paypal_create: MagicMock
    ) -> None:
        """Test creating a pact returns HTTP 201 with serialized pact data and approval URL."""
        self.client.force_authenticate(user=self.buyer)

        mock_paypal_create.return_value = {
            "id": "ORDER-API-100",
            "status": "CREATED",
            "links": [
                {"rel": "approve", "href": "https://sandbox.paypal.com/checkout?token=ORDER-API-100"}
            ],
        }

        payload: dict[str, Any] = {
            "amount": "250.00",
            "currency": "usd",
            "deliverable_type": "JSON_DATASET",
        }

        response = self.client.post(self.create_pact_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("approve_url", response.data)
        self.assertEqual(
            response.data["approve_url"],
            "https://sandbox.paypal.com/checkout?token=ORDER-API-100",
        )
        self.assertIn("pact", response.data)
        self.assertEqual(response.data["pact"]["state"], Pact.State.DRAFT)
        self.assertEqual(response.data["pact"]["paypal_order_id"], "ORDER-API-100")
        self.assertEqual(response.data["pact"]["buyer"], self.buyer.id)

    def test_create_pact_invalid_payload_returns_400(self) -> None:
        """Test invalid payload (missing amount or negative value) returns HTTP 400 Bad Request."""
        self.client.force_authenticate(user=self.buyer)

        # Missing amount
        response_missing = self.client.post(self.create_pact_url, {}, format="json")
        self.assertEqual(response_missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", response_missing.data)

        # Negative amount
        response_negative = self.client.post(
            self.create_pact_url, {"amount": "-10.00"}, format="json"
        )
        self.assertEqual(response_negative.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("escrow.services.pact_service.PayPalService.create_authorization_order")
    def test_create_pact_paypal_failure_returns_400_with_details(
        self, mock_paypal_create: MagicMock
    ) -> None:
        """Test PayPal service failure returns HTTP 400 with error details."""
        self.client.force_authenticate(user=self.buyer)

        mock_paypal_create.side_effect = PayPalAPIException(
            message="PayPal upstream outage",
            status_code=503,
            response_data={"error": "service_unavailable"},
        )

        response = self.client.post(
            self.create_pact_url, {"amount": "100.00", "currency": "USD"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertIn("PayPal upstream outage", response.data["error"])

    # -------------------------------------------------------------------------
    # 3. POST /api/v1/pacts/confirm-authorization/
    # -------------------------------------------------------------------------
    @patch("escrow.services.pact_service.PayPalService.authorize_order")
    def test_confirm_authorization_valid_data_returns_200(
        self, mock_paypal_auth: MagicMock
    ) -> None:
        """Test confirming authorization updates pact to AUTHORIZED and returns HTTP 200."""
        self.client.force_authenticate(user=self.buyer)

        pact = Pact.objects.create(
            buyer=self.buyer,
            amount=Decimal("175.00"),
            state=Pact.State.DRAFT,
            paypal_order_id="ORDER-TO-CONFIRM",
        )

        mock_paypal_auth.return_value = {
            "id": "ORDER-TO-CONFIRM",
            "status": "COMPLETED",
            "purchase_units": [
                {"payments": {"authorizations": [{"id": "AUTH-CONFIRMED-99", "status": "CREATED"}]}}
            ],
        }

        payload: dict[str, Any] = {
            "pact_id": str(pact.id),
            "paypal_order_id": "ORDER-TO-CONFIRM",
        }

        response = self.client.post(self.confirm_auth_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "AUTHORIZED")
        self.assertEqual(response.data["pact"]["state"], Pact.State.AUTHORIZED)

        # Check DB update
        pact.refresh_from_db()
        self.assertEqual(pact.state, Pact.State.AUTHORIZED)
        self.assertEqual(pact.paypal_authorization_id, "AUTH-CONFIRMED-99")

    def test_confirm_authorization_invalid_payload_returns_400(self) -> None:
        """Test missing fields in confirm authorization returns HTTP 400 Bad Request."""
        self.client.force_authenticate(user=self.buyer)

        response = self.client.post(self.confirm_auth_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_authorization_other_user_pact_returns_404(self) -> None:
        """Test a user cannot confirm authorization on another buyer's pact (scoped queryset)."""
        self.client.force_authenticate(user=self.stranger)

        pact = Pact.objects.create(
            buyer=self.buyer,
            amount=Decimal("100.00"),
            state=Pact.State.DRAFT,
            paypal_order_id="ORDER-SECRET",
        )

        payload = {"pact_id": str(pact.id), "paypal_order_id": "ORDER-SECRET"}
        response = self.client.post(self.confirm_auth_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------------------
    # 4. POST /api/v1/pacts/{id}/submit-deliverable/
    # -------------------------------------------------------------------------
    @patch("escrow.services.pact_service.verify_pact_deliverable.delay")
    def test_submit_deliverable_by_designated_seller_returns_202(
        self, mock_task_delay: MagicMock
    ) -> None:
        """Test designated seller submitting deliverable returns HTTP 202 Accepted and updates state."""
        self.client.force_authenticate(user=self.seller)

        pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("500.00"),
            state=Pact.State.AUTHORIZED,
            paypal_authorization_id="AUTH-SELLER-SUBMIT",
        )

        submit_url = reverse("pact-submit-deliverable", kwargs={"pk": pact.id})
        dataset = [{"id": 1, "record": "data A"}, {"id": 2, "record": "data B"}]
        payload = {"payload": dataset}

        response = self.client.post(submit_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["status"], "SUBMITTED")
        self.assertIn("AI outcome verification is in progress", response.data["message"])

        pact.refresh_from_db()
        self.assertEqual(pact.state, Pact.State.SUBMITTED)
        self.assertEqual(pact.deliverable_payload, dataset)

    def test_submit_deliverable_forbidden_for_non_designated_user(self) -> None:
        """Test third-party user cannot submit deliverable when seller is already assigned (HTTP 403)."""
        self.client.force_authenticate(user=self.stranger)

        pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("500.00"),
            state=Pact.State.AUTHORIZED,
        )

        submit_url = reverse("pact-submit-deliverable", kwargs={"pk": pact.id})
        response = self.client.post(submit_url, {"payload": [{"x": 1}]}, format="json")

        # Either 404 (because stranger cannot see pact in get_queryset) or 403
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    @patch("escrow.services.pact_service.verify_pact_deliverable.delay")
    def test_submit_deliverable_assigns_seller_if_initially_unassigned(
        self, mock_task_delay: MagicMock
    ) -> None:
        """Test submitting user is bound as seller if pact.seller was originally None."""
        # Authenticate as the seller who accepts and submits work
        self.client.force_authenticate(user=self.seller)

        pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,  # Visible in scoped queryset
            amount=Decimal("300.00"),
            state=Pact.State.AUTHORIZED,
        )
        # Temporarily clear seller to test lazy assignment logic on pact
        Pact.objects.filter(id=pact.id).update(seller=None)
        pact.refresh_from_db()
        self.assertIsNone(pact.seller)

        submit_url = reverse("pact-submit-deliverable", kwargs={"pk": pact.id})

        # When pact.seller is None, get_queryset for stranger/seller wouldn't match buyer,
        # so test with buyer submitting or verify assignment flow when accessible
        with patch.object(PactViewSet, "get_queryset") as mock_qs:
            mock_qs.return_value = Pact.objects.filter(id=pact.id)
            response = self.client.post(
                submit_url,
                {"payload": [{"record": "first"}, {"record": "second"}]},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        pact.refresh_from_db()
        self.assertEqual(pact.seller, self.seller)

    def test_submit_deliverable_empty_payload_returns_400(self) -> None:
        """Test submitting empty payload returns HTTP 400 Bad Request."""
        self.client.force_authenticate(user=self.seller)

        pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("100.00"),
            state=Pact.State.AUTHORIZED,
        )

        submit_url = reverse("pact-submit-deliverable", kwargs={"pk": pact.id})
        response = self.client.post(submit_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)


class PayPalWebhookAPITests(APITestCase):
    """Integration tests for PayPalWebhookView endpoint."""

    def setUp(self) -> None:
        """Set up test users, sample pact, and webhook URL."""
        self.buyer = User.objects.create_user(email="buyer_webhook@example.com", password="password123")
        self.seller = User.objects.create_user(email="seller_webhook@example.com", password="password123")
        self.webhook_url = reverse("paypal-webhook")
        self.valid_headers = {
            "HTTP_PAYPAL_AUTH_ALGO": "SHA256withRSA",
            "HTTP_PAYPAL_CERT_URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-123",
            "HTTP_PAYPAL_TRANSMISSION_ID": "trans-123-abc",
            "HTTP_PAYPAL_TRANSMISSION_SIG": "sig-xyz-789",
            "HTTP_PAYPAL_TRANSMISSION_TIME": "2026-10-12T20:50:00Z",
        }

    def test_webhook_missing_headers_returns_400(self) -> None:
        """Asserts HTTP 400 when required PayPal transmission headers are omitted."""
        # Post with no PayPal headers
        response = self.client.post(
            self.webhook_url,
            {"event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "ORDER-123"}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Missing required PayPal signature header", response.data["error"])

    @patch("escrow.services.paypal_service.PayPalService.verify_webhook_signature")
    def test_webhook_invalid_signature_returns_400(self, mock_verify: MagicMock) -> None:
        """Mock verify_webhook_signature returning False, assert HTTP 400."""
        mock_verify.return_value = False

        payload = {"event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "ORDER-123"}}
        response = self.client.post(
            self.webhook_url,
            payload,
            format="json",
            **self.valid_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid webhook signature", response.data["error"])

    @patch("escrow.services.paypal_service.PayPalService.authorize_order")
    @patch("escrow.services.paypal_service.PayPalService.verify_webhook_signature")
    def test_webhook_checkout_order_approved_authorizes_draft_pact(
        self, mock_verify: MagicMock, mock_authorize: MagicMock
    ) -> None:
        """Mock signature valid, mock authorize_order, assert Pact transitions from DRAFT to AUTHORIZED and writes to PactLedger."""
        mock_verify.return_value = True
        mock_authorize.return_value = {
            "id": "ORDER-WEBHOOK-99",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "authorizations": [
                            {"id": "AUTH-WEBHOOK-456", "status": "CREATED"}
                        ]
                    }
                }
            ],
        }

        pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("350.00"),
            state=Pact.State.DRAFT,
            paypal_order_id="ORDER-WEBHOOK-99",
        )

        payload = {
            "id": "WH-EVT-001",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": "ORDER-WEBHOOK-99"},
        }

        response = self.client.post(
            self.webhook_url,
            payload,
            format="json",
            **self.valid_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "acknowledged")

        # Verify pact state transition
        pact.refresh_from_db()
        self.assertEqual(pact.state, Pact.State.AUTHORIZED)
        self.assertEqual(pact.paypal_authorization_id, "AUTH-WEBHOOK-456")

        # Verify ledger audit entry
        ledger = PactLedger.objects.filter(pact=pact, action="AUTHORIZED_VIA_WEBHOOK").first()
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger.details["paypal_order_id"], "ORDER-WEBHOOK-99")
        self.assertEqual(ledger.details["paypal_authorization_id"], "AUTH-WEBHOOK-456")
        self.assertEqual(ledger.details["webhook_event_id"], "WH-EVT-001")

    @patch("escrow.services.paypal_service.PayPalService.verify_webhook_signature")
    def test_webhook_authorization_voided_updates_pact_state(
        self, mock_verify: MagicMock
    ) -> None:
        """Mock signature valid, assert Pact transitions to VOIDED and writes to PactLedger."""
        mock_verify.return_value = True

        pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("500.00"),
            state=Pact.State.AUTHORIZED,
            paypal_authorization_id="AUTH-TO-VOID-123",
        )

        payload = {
            "id": "WH-EVT-002",
            "event_type": "PAYMENT.AUTHORIZATION.VOIDED",
            "resource": {"id": "AUTH-TO-VOID-123"},
        }

        response = self.client.post(
            self.webhook_url,
            payload,
            format="json",
            **self.valid_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "acknowledged")

        # Verify pact state transition
        pact.refresh_from_db()
        self.assertEqual(pact.state, Pact.State.VOIDED)

        # Verify ledger audit entry
        ledger = PactLedger.objects.filter(pact=pact, action="FUNDS_VOIDED_EXTERNALLY").first()
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger.details["paypal_authorization_id"], "AUTH-TO-VOID-123")
        self.assertEqual(ledger.details["previous_state"], Pact.State.AUTHORIZED)
        self.assertEqual(ledger.details["webhook_event_id"], "WH-EVT-002")

