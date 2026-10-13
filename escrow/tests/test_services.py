"""Unit tests for escrow service layer (PayPalService and PactService)."""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
import requests

from escrow.models import Pact, PactLedger
from escrow.services.pact_service import PactService
from escrow.services.paypal_service import PayPalAPIException, PayPalService

User = get_user_model()


class PayPalServiceTests(TestCase):
    """Unit tests for PayPal REST API service client."""

    def setUp(self) -> None:
        """Clear cache and initialize PayPal service before each test."""
        cache.clear()
        self.service: PayPalService = PayPalService()
        self.service.client_id = "test_client_id"
        self.service.client_secret = "test_client_secret"
        self.service.base_url = "https://api-m.sandbox.paypal.com"

    def tearDown(self) -> None:
        """Clear cache after each test."""
        cache.clear()

    @patch("requests.post")
    def test_get_access_token_success_and_caching(self, mock_post: MagicMock) -> None:
        """Test token acquisition and verify caching prevents redundant network calls."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mock_access_token_xyz",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        # 1. First invocation: makes network call and caches token
        token: str = self.service._get_access_token()
        self.assertEqual(token, "mock_access_token_xyz")
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(cache.get(PayPalService.CACHE_KEY_TOKEN), "mock_access_token_xyz")

        # 2. Second invocation: retrieves cached token without network request
        cached_token: str = self.service._get_access_token()
        self.assertEqual(cached_token, "mock_access_token_xyz")
        self.assertEqual(mock_post.call_count, 1)

    @patch("requests.post")
    def test_get_access_token_http_error_raises_exception(self, mock_post: MagicMock) -> None:
        """Test HTTP 401 response from PayPal auth raises PayPalAPIException."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "invalid_client", "error_description": "Client authentication failed"}
        mock_post.return_value = mock_response

        with self.assertRaises(PayPalAPIException) as ctx:
            self.service._get_access_token()

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("Failed to obtain PayPal OAuth access token", ctx.exception.message)

    @patch("requests.post")
    def test_get_access_token_network_exception(self, mock_post: MagicMock) -> None:
        """Test network connectivity failure raises PayPalAPIException."""
        mock_post.side_effect = requests.RequestException("Connection timeout")

        with self.assertRaises(PayPalAPIException) as ctx:
            self.service._get_access_token()

        self.assertIn("Connection failure during authentication", ctx.exception.message)

    @patch.object(PayPalService, "_get_access_token", return_value="mock_token")
    @patch("requests.post")
    def test_create_authorization_order_success(
        self, mock_post: MagicMock, mock_token: MagicMock
    ) -> None:
        """Test creating an authorization order sends correct intent, amount, and returns data."""
        user = User.objects.create_user(email="buyer@example.com", password="password123")
        pact = Pact.objects.create(
            buyer=user,
            amount=Decimal("150.00"),
            currency="USD",
            deliverable_type="JSON_DATASET",
        )

        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = True
        mock_response.status_code = 201
        expected_payload = {
            "id": "ORDER-999",
            "status": "CREATED",
            "links": [
                {"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-999"},
                {"rel": "self", "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/ORDER-999"},
            ],
        }
        mock_response.json.return_value = expected_payload
        mock_post.return_value = mock_response

        result: dict[str, Any] = self.service.create_authorization_order(pact)

        self.assertEqual(result["id"], "ORDER-999")
        self.assertEqual(result["status"], "CREATED")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["intent"], "AUTHORIZE")
        self.assertEqual(kwargs["json"]["purchase_units"][0]["amount"]["value"], "150.00")
        self.assertEqual(kwargs["json"]["purchase_units"][0]["amount"]["currency_code"], "USD")

    @patch.object(PayPalService, "_get_access_token", return_value="mock_token")
    @patch("requests.post")
    def test_create_authorization_order_http_error(
        self, mock_post: MagicMock, mock_token: MagicMock
    ) -> None:
        """Test HTTP 400 from PayPal order creation raises PayPalAPIException."""
        user = User.objects.create_user(email="buyer_err@example.com", password="password123")
        pact = Pact.objects.create(
            buyer=user,
            amount=Decimal("50.00"),
            currency="USD",
        )

        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {"name": "INVALID_REQUEST", "message": "Request is invalid"}
        mock_post.return_value = mock_response

        with self.assertRaises(PayPalAPIException) as ctx:
            self.service.create_authorization_order(pact)

        self.assertEqual(ctx.exception.status_code, 400)

    @patch.object(PayPalService, "_get_access_token", return_value="mock_token")
    @patch("requests.post")
    def test_authorize_order_success(
        self, mock_post: MagicMock, mock_token: MagicMock
    ) -> None:
        """Test authorizing an order returns authorization data payload."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "ORDER-999",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "authorizations": [
                            {"id": "AUTH-777", "status": "CREATED", "amount": {"value": "150.00", "currency_code": "USD"}}
                        ]
                    }
                }
            ],
        }
        mock_post.return_value = mock_response

        result: dict[str, Any] = self.service.authorize_order("ORDER-999")

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["purchase_units"][0]["payments"]["authorizations"][0]["id"], "AUTH-777")

    def test_authorize_order_empty_id_raises_value_error(self) -> None:
        """Test passing empty order_id raises ValueError."""
        with self.assertRaises(ValueError):
            self.service.authorize_order("")

    @patch.object(PayPalService, "_get_access_token", return_value="mock_token")
    @patch("requests.post")
    def test_authorize_order_http_error(
        self, mock_post: MagicMock, mock_token: MagicMock
    ) -> None:
        """Test HTTP 422 error during order authorization raises PayPalAPIException."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = False
        mock_response.status_code = 422
        mock_response.json.return_value = {"name": "UNPROCESSABLE_ENTITY", "message": "Order already authorized"}
        mock_post.return_value = mock_response

        with self.assertRaises(PayPalAPIException) as ctx:
            self.service.authorize_order("ORDER-999")

        self.assertEqual(ctx.exception.status_code, 422)

    @patch.object(PayPalService, "_get_access_token", return_value="mock_token")
    @patch("requests.post")
    def test_capture_authorization_success(
        self, mock_post: MagicMock, mock_token: MagicMock
    ) -> None:
        """Test capturing authorization posts to endpoint and returns capture info."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "CAPTURE-111",
            "status": "COMPLETED",
            "amount": {"value": "150.00", "currency_code": "USD"},
        }
        mock_post.return_value = mock_response

        result: dict[str, Any] = self.service.capture_authorization("AUTH-777")

        self.assertEqual(result["id"], "CAPTURE-111")
        self.assertEqual(result["status"], "COMPLETED")
        mock_post.assert_called_once()
        self.assertIn("authorizations/AUTH-777/capture", mock_post.call_args[0][0])

    def test_capture_authorization_empty_id_raises_value_error(self) -> None:
        """Test passing empty authorization_id raises ValueError."""
        with self.assertRaises(ValueError):
            self.service.capture_authorization("")

    @patch.object(PayPalService, "_get_access_token", return_value="mock_token")
    @patch("requests.post")
    def test_capture_authorization_http_error(
        self, mock_post: MagicMock, mock_token: MagicMock
    ) -> None:
        """Test HTTP 500 error during capture raises PayPalAPIException."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.json.return_value = {"name": "INTERNAL_SERVER_ERROR"}
        mock_post.return_value = mock_response

        with self.assertRaises(PayPalAPIException) as ctx:
            self.service.capture_authorization("AUTH-777")

        self.assertEqual(ctx.exception.status_code, 500)

    @patch.object(PayPalService, "_get_access_token", return_value="mock_token")
    @patch("requests.post")
    def test_void_authorization_204_success(
        self, mock_post: MagicMock, mock_token: MagicMock
    ) -> None:
        """Test voiding authorization with HTTP 204 No Content returns expected status dict."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = True
        mock_response.status_code = 204
        mock_response.content = b""
        mock_post.return_value = mock_response

        result: dict[str, Any] = self.service.void_authorization("AUTH-777")

        self.assertEqual(result["status"], "VOIDED")
        self.assertEqual(result["authorization_id"], "AUTH-777")

    def test_void_authorization_empty_id_raises_value_error(self) -> None:
        """Test passing empty authorization_id raises ValueError."""
        with self.assertRaises(ValueError):
            self.service.void_authorization("")

    @patch.object(PayPalService, "_get_access_token", return_value="mock_token")
    @patch("requests.post")
    def test_void_authorization_http_error(
        self, mock_post: MagicMock, mock_token: MagicMock
    ) -> None:
        """Test HTTP 400 error during void raises PayPalAPIException."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.json.return_value = {"name": "PRECONDITION_FAILED"}
        mock_post.return_value = mock_response

        with self.assertRaises(PayPalAPIException) as ctx:
            self.service.void_authorization("AUTH-777")

        self.assertEqual(ctx.exception.status_code, 400)


class PactServiceTests(TestCase):
    """Unit tests for PactService domain business logic."""

    def setUp(self) -> None:
        """Create sample users and initialize PactService."""
        self.buyer = User.objects.create_user(email="pact_buyer@example.com", password="password123")
        self.seller = User.objects.create_user(email="pact_seller@example.com", password="password123")
        self.pact_service: PactService = PactService()

    @patch.object(PayPalService, "create_authorization_order")
    def test_create_draft_pact_success(self, mock_paypal_create: MagicMock) -> None:
        """Test creating a draft pact persists record, saves order id, and logs PACT_CREATED."""
        mock_paypal_create.return_value = {
            "id": "ORDER-555",
            "status": "CREATED",
            "links": [
                {"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-555"}
            ],
        }

        pact, approve_url = self.pact_service.create_draft_pact(
            buyer=self.buyer,
            amount=Decimal("200.00"),
            currency="USD",
            deliverable_type="JSON_DATASET",
            seller=self.seller,
        )

        # Assert pact persistence and attributes
        self.assertEqual(pact.state, Pact.State.DRAFT)
        self.assertEqual(pact.buyer, self.buyer)
        self.assertEqual(pact.seller, self.seller)
        self.assertEqual(pact.amount, Decimal("200.00"))
        self.assertEqual(pact.paypal_order_id, "ORDER-555")
        self.assertEqual(approve_url, "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-555")

        # Assert ledger logging
        ledger_entry = PactLedger.objects.filter(pact=pact, action="PACT_CREATED").first()
        self.assertIsNotNone(ledger_entry)
        self.assertEqual(ledger_entry.details["paypal_order_id"], "ORDER-555")
        self.assertEqual(ledger_entry.details["approve_url"], approve_url)

    @patch.object(PayPalService, "create_authorization_order")
    def test_create_draft_pact_missing_approve_link_raises_exception(
        self, mock_paypal_create: MagicMock
    ) -> None:
        """Test PayPal response missing approve link raises PayPalAPIException."""
        mock_paypal_create.return_value = {
            "id": "ORDER-555",
            "status": "CREATED",
            "links": [{"rel": "self", "href": "https://api.sandbox.paypal.com"}],
        }

        with self.assertRaises(PayPalAPIException):
            self.pact_service.create_draft_pact(
                buyer=self.buyer,
                amount=Decimal("100.00"),
            )

    @patch.object(PayPalService, "authorize_order")
    def test_confirm_pact_authorization_success(self, mock_paypal_auth: MagicMock) -> None:
        """Test confirming authorization transitions state to AUTHORIZED and logs event."""
        pact = Pact.objects.create(
            buyer=self.buyer,
            amount=Decimal("300.00"),
            currency="USD",
            state=Pact.State.DRAFT,
            paypal_order_id="ORDER-777",
        )

        mock_paypal_auth.return_value = {
            "id": "ORDER-777",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "authorizations": [
                            {"id": "AUTH-888", "status": "CREATED"}
                        ]
                    }
                }
            ],
        }

        updated_pact: Pact = self.pact_service.confirm_pact_authorization(pact, "ORDER-777")

        self.assertEqual(updated_pact.state, Pact.State.AUTHORIZED)
        self.assertEqual(updated_pact.paypal_authorization_id, "AUTH-888")

        ledger_entry = PactLedger.objects.filter(pact=updated_pact, action="AUTHORIZED").first()
        self.assertIsNotNone(ledger_entry)
        self.assertEqual(ledger_entry.details["paypal_authorization_id"], "AUTH-888")

    def test_confirm_pact_authorization_invalid_state_raises_value_error(self) -> None:
        """Test confirming a pact that is not in DRAFT state raises ValueError."""
        pact = Pact.objects.create(
            buyer=self.buyer,
            amount=Decimal("100.00"),
            state=Pact.State.AUTHORIZED,
            paypal_order_id="ORDER-111",
        )

        with self.assertRaises(ValueError) as ctx:
            self.pact_service.confirm_pact_authorization(pact, "ORDER-111")

        self.assertIn("Expected DRAFT", str(ctx.exception))

    def test_confirm_pact_authorization_order_mismatch_raises_value_error(self) -> None:
        """Test confirming a pact with mismatched order_id raises ValueError."""
        pact = Pact.objects.create(
            buyer=self.buyer,
            amount=Decimal("100.00"),
            state=Pact.State.DRAFT,
            paypal_order_id="ORDER-RECORDED",
        )

        with self.assertRaises(ValueError) as ctx:
            self.pact_service.confirm_pact_authorization(pact, "ORDER-DIFFERENT")

        self.assertIn("mismatch", str(ctx.exception).lower())

    @patch("escrow.services.pact_service.verify_pact_deliverable.delay")
    def test_submit_pact_deliverable_success(self, mock_task_delay: MagicMock) -> None:
        """Test submitting deliverable transitions state to SUBMITTED and enqueues task."""
        pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("250.00"),
            state=Pact.State.AUTHORIZED,
            paypal_authorization_id="AUTH-999",
        )

        payload = {"dataset": [{"id": 1, "text": "sample A"}, {"id": 2, "text": "sample B"}]}

        with self.captureOnCommitCallbacks(execute=True):
            updated_pact = self.pact_service.submit_pact_deliverable(pact, payload)

        self.assertEqual(updated_pact.state, Pact.State.SUBMITTED)
        self.assertEqual(updated_pact.deliverable_payload, payload)

        # Assert ledger entry
        ledger_entry = PactLedger.objects.filter(pact=updated_pact, action="DELIVERABLE_SUBMITTED").first()
        self.assertIsNotNone(ledger_entry)

        # Assert Celery task triggered
        mock_task_delay.assert_called_once_with(str(pact.id))

    def test_submit_pact_deliverable_when_not_authorized_raises_value_error(self) -> None:
        """Verify submitting deliverables when not in AUTHORIZED state raises ValueError."""
        invalid_states = [
            Pact.State.DRAFT,
            Pact.State.SUBMITTED,
            Pact.State.IN_REVIEW,
            Pact.State.CAPTURED,
            Pact.State.VOIDED,
            Pact.State.REJECTED,
        ]

        for state in invalid_states:
            with self.subTest(state=state):
                pact = Pact.objects.create(
                    buyer=self.buyer,
                    seller=self.seller,
                    amount=Decimal("100.00"),
                    state=state,
                )
                with self.assertRaises(ValueError) as ctx:
                    self.pact_service.submit_pact_deliverable(pact, {"key": "val"})

                self.assertIn("Pact must be in AUTHORIZED state", str(ctx.exception))

    def test_submit_pact_deliverable_empty_payload_raises_value_error(self) -> None:
        """Test submitting empty payload raises ValueError."""
        pact = Pact.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("100.00"),
            state=Pact.State.AUTHORIZED,
        )

        with self.assertRaises(ValueError) as ctx:
            self.pact_service.submit_pact_deliverable(pact, {})

        self.assertIn("Deliverable payload cannot be empty", str(ctx.exception))
