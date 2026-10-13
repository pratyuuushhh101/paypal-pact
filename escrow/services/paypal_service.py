"""Production-grade PayPal REST API service layer for escrow transactions."""

import json
import logging
from typing import TYPE_CHECKING, Any
from django.conf import settings
from django.core.cache import cache
import requests
from requests.auth import HTTPBasicAuth

if TYPE_CHECKING:
    from escrow.models import Pact

logger = logging.getLogger(__name__)


class PayPalAPIException(Exception):
    """Custom exception raised when PayPal API encounters client, server, or transport errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict[str, Any] | str | None = None,
    ) -> None:
        super().__init__(message)
        self.message: str = message
        self.status_code: int | None = status_code
        self.response_data: dict[str, Any] | str | None = response_data

    def __str__(self) -> str:
        if self.status_code:
            return f"[PayPal Error {self.status_code}] {self.message} - Response: {self.response_data}"
        return f"[PayPal Error] {self.message}"


class PayPalService:
    """Service client orchestrating authentication, authorization, capture, and void flows via PayPal REST API v2."""

    SANDBOX_URL: str = "https://api-m.sandbox.paypal.com"
    LIVE_URL: str = "https://api-m.paypal.com"
    CACHE_KEY_TOKEN: str = "paypal_access_token"
    DEFAULT_TIMEOUT: int = 30  # seconds

    def __init__(self) -> None:
        """Initialize PayPal service with credentials and target environment."""
        self.client_id: str = getattr(settings, "PAYPAL_CLIENT_ID", "")
        self.client_secret: str = getattr(settings, "PAYPAL_CLIENT_SECRET", "")
        self.environment: str = getattr(settings, "PAYPAL_ENVIRONMENT", "sandbox").strip().lower()

        if not self.client_id or not self.client_secret:
            logger.warning("PayPal client credentials are not configured in settings.")

        self.base_url: str = self.LIVE_URL if self.environment == "live" else self.SANDBOX_URL

    def _get_access_token(self) -> str:
        """Fetch bearer access token using client credentials and cache it until expiration.

        Returns:
            Valid PayPal Bearer access token string.

        Raises:
            PayPalAPIException: If token generation fails.
        """
        cached_token: str | None = cache.get(self.CACHE_KEY_TOKEN)
        if cached_token:
            return cached_token

        endpoint: str = f"{self.base_url}/v1/oauth2/token"
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        data: dict[str, str] = {
            "grant_type": "client_credentials",
        }

        logger.info("Requesting new PayPal OAuth2 access token from %s", endpoint)
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                data=data,
                auth=HTTPBasicAuth(self.client_id, self.client_secret),
                timeout=self.DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.exception("Failed to connect to PayPal OAuth endpoint: %s", exc)
            raise PayPalAPIException(f"Connection failure during authentication: {exc}") from exc

        if not response.ok:
            error_details = self._parse_response_body(response)
            logger.error(
                "PayPal OAuth request failed. Status: %s, Response: %s",
                response.status_code,
                error_details,
            )
            raise PayPalAPIException(
                message="Failed to obtain PayPal OAuth access token.",
                status_code=response.status_code,
                response_data=error_details,
            )

        token_payload: dict[str, Any] = response.json()
        token: str = token_payload.get("access_token", "")
        expires_in: int = int(token_payload.get("expires_in", 3600))

        if not token:
            raise PayPalAPIException("PayPal OAuth response omitted access_token.")

        # Cache token with a 60-second safety cushion before actual expiration
        cache_ttl = max(expires_in - 60, 60)
        cache.set(self.CACHE_KEY_TOKEN, token, timeout=cache_ttl)
        logger.info("Successfully acquired and cached PayPal OAuth2 token for %s seconds.", cache_ttl)

        return token

    def _get_authenticated_headers(self) -> dict[str, str]:
        """Generate common headers with authorization bearer token.

        Returns:
            Dict containing authorization and content type headers.
        """
        token: str = self._get_access_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

    @staticmethod
    def _parse_response_body(response: requests.Response) -> dict[str, Any] | str:
        """Parse response JSON safely or return raw text fallback.

        Args:
            response: requests.Response object.

        Returns:
            Parsed JSON dict or raw string.
        """
        try:
            return response.json()
        except ValueError:
            return response.text

    def create_authorization_order(self, pact: "Pact") -> dict[str, Any]:
        """Create an order with intent: AUTHORIZE for a given Pact.

        Args:
            pact: The Pact model instance containing amount, currency, and ID.

        Returns:
            Parsed PayPal order response data.

        Raises:
            PayPalAPIException: If order creation returns 4xx or 5xx.
        """
        endpoint: str = f"{self.base_url}/v2/checkout/orders"
        headers: dict[str, str] = self._get_authenticated_headers()

        formatted_amount: str = f"{pact.amount:.2f}"
        payload: dict[str, Any] = {
            "intent": "AUTHORIZE",
            "purchase_units": [
                {
                    "reference_id": str(pact.id),
                    "custom_id": str(pact.id),
                    "description": f"Escrow Pact {pact.id} [{pact.deliverable_type}]",
                    "amount": {
                        "currency_code": pact.currency,
                        "value": formatted_amount,
                    },
                }
            ],
        }

        logger.info("Creating PayPal authorization order for Pact %s (amount: %s %s)", pact.id, formatted_amount, pact.currency)

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=self.DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.exception("Network failure during PayPal order creation for Pact %s: %s", pact.id, exc)
            raise PayPalAPIException(f"Network error creating PayPal order: {exc}") from exc

        if not response.ok:
            error_details = self._parse_response_body(response)
            logger.error(
                "PayPal order creation failed for Pact %s. Status: %s, Response: %s",
                pact.id,
                response.status_code,
                error_details,
            )
            raise PayPalAPIException(
                message=f"PayPal order creation failed with status {response.status_code}",
                status_code=response.status_code,
                response_data=error_details,
            )

        data: dict[str, Any] = response.json()
        logger.info("Successfully created PayPal order %s for Pact %s", data.get("id"), pact.id)
        return data

    def authorize_order(self, order_id: str) -> dict[str, Any]:
        """Authorize payment for an approved PayPal order.

        Args:
            order_id: The PayPal order ID approved by the buyer.

        Returns:
            Parsed PayPal order authorization response payload containing authorization IDs.

        Raises:
            ValueError: If order_id is empty.
            PayPalAPIException: If authorization request returns 4xx or 5xx.
        """
        if not order_id:
            raise ValueError("order_id cannot be empty.")

        endpoint: str = f"{self.base_url}/v2/checkout/orders/{order_id}/authorize"
        headers: dict[str, str] = self._get_authenticated_headers()

        logger.info("Executing authorization for approved PayPal order: %s", order_id)

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json={},
                timeout=self.DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.exception("Network error authorizing order %s: %s", order_id, exc)
            raise PayPalAPIException(f"Network error authorizing order {order_id}: {exc}") from exc

        if not response.ok:
            error_details = self._parse_response_body(response)
            logger.error(
                "PayPal order authorization failed for order %s. Status: %s, Response: %s",
                order_id,
                response.status_code,
                error_details,
            )
            raise PayPalAPIException(
                message=f"Failed to authorize PayPal order {order_id}",
                status_code=response.status_code,
                response_data=error_details,
            )

        data: dict[str, Any] = response.json()
        logger.info("Successfully authorized PayPal order %s (status: %s)", order_id, data.get("status"))
        return data

    def capture_authorization(self, authorization_id: str) -> dict[str, Any]:
        """Capture funds from a previously authorized payment.

        Args:
            authorization_id: The PayPal authorization identifier to capture.

        Returns:
            PayPal capture response payload.

        Raises:
            PayPalAPIException: If capture request returns 4xx or 5xx.
        """
        if not authorization_id:
            raise ValueError("authorization_id cannot be empty.")

        endpoint: str = f"{self.base_url}/v2/payments/authorizations/{authorization_id}/capture"
        headers: dict[str, str] = self._get_authenticated_headers()

        logger.info("Requesting capture on authorization ID: %s", authorization_id)

        try:
            # PayPal capture endpoint accepts empty body or final_capture flag
            response = requests.post(
                endpoint,
                headers=headers,
                json={"final_capture": True},
                timeout=self.DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.exception("Network error capturing authorization %s: %s", authorization_id, exc)
            raise PayPalAPIException(f"Network error capturing authorization {authorization_id}: {exc}") from exc

        if not response.ok:
            error_details = self._parse_response_body(response)
            logger.error(
                "PayPal authorization capture failed for %s. Status: %s, Response: %s",
                authorization_id,
                response.status_code,
                error_details,
            )
            raise PayPalAPIException(
                message=f"Failed to capture PayPal authorization {authorization_id}",
                status_code=response.status_code,
                response_data=error_details,
            )

        data: dict[str, Any] = response.json()
        logger.info("Successfully captured authorization %s (Capture ID: %s)", authorization_id, data.get("id"))
        return data

    def void_authorization(self, authorization_id: str) -> dict[str, Any]:
        """Void an active authorization to release held funds back to buyer.

        Args:
            authorization_id: The PayPal authorization identifier to void.

        Returns:
            PayPal void response payload or confirmation dict.

        Raises:
            PayPalAPIException: If void request returns 4xx or 5xx.
        """
        if not authorization_id:
            raise ValueError("authorization_id cannot be empty.")

        endpoint: str = f"{self.base_url}/v2/payments/authorizations/{authorization_id}/void"
        headers: dict[str, str] = self._get_authenticated_headers()

        logger.info("Requesting void on authorization ID: %s", authorization_id)

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                timeout=self.DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.exception("Network error voiding authorization %s: %s", authorization_id, exc)
            raise PayPalAPIException(f"Network error voiding authorization {authorization_id}: {exc}") from exc

        # PayPal returns 204 No Content upon successful void
        if response.status_code == 204:
            logger.info("Successfully voided authorization %s (204 No Content)", authorization_id)
            return {"status": "VOIDED", "authorization_id": authorization_id}

        if not response.ok:
            error_details = self._parse_response_body(response)
            logger.error(
                "PayPal authorization void failed for %s. Status: %s, Response: %s",
                authorization_id,
                response.status_code,
                error_details,
            )
            raise PayPalAPIException(
                message=f"Failed to void PayPal authorization {authorization_id}",
                status_code=response.status_code,
                response_data=error_details,
            )

        data: dict[str, Any] = response.json() if response.content else {"status": "VOIDED"}
        logger.info("Successfully voided authorization %s", authorization_id)
        return data

    def verify_webhook_signature(
        self,
        headers: dict[str, str],
        raw_body: str,
        webhook_id: str,
    ) -> bool:
        """Verify the cryptographic signature of an incoming PayPal webhook notification.

        Args:
            headers: Dictionary containing HTTP request headers.
            raw_body: Raw unparsed request body string.
            webhook_id: Configured PayPal Webhook ID.

        Returns:
            bool: True if PayPal confirms the signature status is SUCCESS, False otherwise.
        """
        if not webhook_id:
            logger.warning("PayPal Webhook ID is not configured. Webhook signature verification rejected.")
            return False

        # Support case-insensitive header access
        norm_headers: dict[str, str] = {k.upper(): v for k, v in headers.items()}
        auth_algo: str | None = norm_headers.get("PAYPAL-AUTH-ALGO")
        cert_url: str | None = norm_headers.get("PAYPAL-CERT-URL")
        transmission_id: str | None = norm_headers.get("PAYPAL-TRANSMISSION-ID")
        transmission_sig: str | None = norm_headers.get("PAYPAL-TRANSMISSION-SIG")
        transmission_time: str | None = norm_headers.get("PAYPAL-TRANSMISSION-TIME")

        if not all([auth_algo, cert_url, transmission_id, transmission_sig, transmission_time]):
            logger.warning("Missing required PayPal signature headers for webhook verification.")
            return False

        try:
            webhook_event: Any = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to decode raw body as JSON for webhook verification: %s", exc)
            return False

        endpoint: str = f"{self.base_url}/v1/notifications/verify-webhook-signature"
        try:
            auth_headers: dict[str, str] = self._get_authenticated_headers()
        except PayPalAPIException as exc:
            logger.exception("Failed to obtain access token for webhook signature verification: %s", exc)
            return False

        verification_payload: dict[str, Any] = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": webhook_id,
            "webhook_event": webhook_event,
        }

        logger.info(
            "Sending webhook verification request for transmission_id: %s to %s",
            transmission_id,
            endpoint,
        )

        try:
            response = requests.post(
                endpoint,
                headers=auth_headers,
                json=verification_payload,
                timeout=self.DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.exception("Network error during PayPal webhook signature verification: %s", exc)
            return False

        if not response.ok:
            error_details = self._parse_response_body(response)
            logger.error(
                "PayPal webhook signature verification endpoint failed. Status: %s, Response: %s",
                response.status_code,
                error_details,
            )
            return False

        try:
            result: dict[str, Any] = response.json()
            status: str | None = result.get("verification_status")
            logger.info("PayPal webhook verification status: %s", status)
            return status == "SUCCESS"
        except (ValueError, TypeError) as exc:
            logger.error("Failed to parse JSON response from PayPal webhook verification endpoint: %s", exc)
            return False

