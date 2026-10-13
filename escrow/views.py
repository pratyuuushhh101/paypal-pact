import json
import logging
from typing import Any
from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Pact, PactLedger
from .serializers import (
    ConfirmAuthorizationRequestSerializer,
    CreatePactRequestSerializer,
    PactSerializer,
    SubmitDeliverableRequestSerializer,
)
from .services import PayPalAPIException, PayPalService, PactService

logger = logging.getLogger(__name__)


class PactViewSet(viewsets.ModelViewSet):
    """ViewSet handling CRUD actions and custom escrow lifecycle events for Pacts."""

    serializer_class = PactSerializer
    permission_classes = [IsAuthenticated]
    queryset = Pact.objects.select_related("buyer", "seller").prefetch_related("ledger_entries").all()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize ViewSet with injected business logic service."""
        super().__init__(*args, **kwargs)
        self.pact_service: PactService = PactService()

    def get_queryset(self) -> QuerySet[Pact]:
        """Scope visible pacts to those where the authenticated user is buyer or seller."""
        user = self.request.user
        return self.queryset.filter(Q(buyer=user) | Q(seller=user))

    @action(detail=False, methods=["post"], url_path="create-pact")
    def create_pact(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a new Pact draft and initiate PayPal authorization.

        Request Body:
            amount (Decimal): Agreement total.
            currency (str, optional): ISO currency code (default: USD).
            deliverable_type (str, optional): Deliverable identifier (default: JSON_DATASET).

        Returns:
            HTTP 201: Serialized pact data and PayPal buyer approval URL.
            HTTP 400: Validation or PayPal API failure.
        """
        request_serializer = CreatePactRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            pact, approve_url = self.pact_service.create_draft_pact(
                buyer=request.user,
                amount=validated_data["amount"],
                currency=validated_data.get("currency", "USD"),
                deliverable_type=validated_data.get("deliverable_type", "JSON_DATASET"),
            )
        except PayPalAPIException as exc:
            return Response(
                {
                    "error": exc.message,
                    "details": exc.response_data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(pact)
        return Response(
            {
                "pact": serializer.data,
                "approve_url": approve_url,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="confirm-authorization")
    def confirm_authorization(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Confirm PayPal authorization after buyer approves payment on PayPal.

        Request Body:
            pact_id (UUID): The target pact ID.
            paypal_order_id (str): The approved PayPal order ID.

        Returns:
            HTTP 200: Updated pact in AUTHORIZED state.
            HTTP 400: PayPal API failure, state conflict, or mismatch.
        """
        request_serializer = ConfirmAuthorizationRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        pact: Pact = get_object_or_404(
            Pact,
            id=validated_data["pact_id"],
            buyer=request.user,
        )

        try:
            updated_pact = self.pact_service.confirm_pact_authorization(
                pact=pact,
                order_id=validated_data["paypal_order_id"],
            )
        except (PayPalAPIException, ValueError) as exc:
            error_message = exc.message if isinstance(exc, PayPalAPIException) else str(exc)
            error_details = exc.response_data if isinstance(exc, PayPalAPIException) else None
            return Response(
                {
                    "error": error_message,
                    "details": error_details,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(updated_pact)
        return Response(
            {
                "status": "AUTHORIZED",
                "message": "Pact authorization confirmed successfully.",
                "pact": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="submit-deliverable")
    def submit_deliverable(self, request: Request, pk: str | None = None) -> Response:
        """Submit seller deliverable payload and enqueue background AI verification.

        Request Body:
            payload (dict | Any): The deliverable data payload or dataset. Supports either
                                  {"payload": {...}} wrapper or raw JSON object.

        Returns:
            HTTP 202: Deliverable accepted and queued for outcome verification.
            HTTP 400: Validation or state conflict error.
            HTTP 403: If user is not the designated seller for this pact.
        """
        pact: Pact = self.get_object()

        # Enforce that only the assigned seller can submit work (if seller is assigned)
        if pact.seller and pact.seller != request.user:
            return Response(
                {"error": "Only the designated seller can submit deliverables for this pact."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Support either {"payload": {...}} wrapper or raw body dictionary
        if isinstance(request.data, dict) and "payload" in request.data:
            payload = request.data["payload"]
        else:
            payload = request.data

        if not payload:
            return Response(
                {"error": "A non-empty deliverable payload must be provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Bind the submitting user as seller if not assigned during draft
            if not pact.seller:
                pact.seller = request.user
                pact.save(update_fields=["seller", "updated_at"])

            updated_pact = self.pact_service.submit_pact_deliverable(
                pact=pact,
                payload=payload,
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(updated_pact)
        return Response(
            {
                "status": "SUBMITTED",
                "message": "Deliverable successfully received. AI outcome verification is in progress.",
                "pact": serializer.data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class PayPalWebhookView(APIView):
    """Webhook endpoint handling asynchronous PayPal event notifications with cryptographic verification."""

    permission_classes = [AllowAny]

    REQUIRED_HEADERS: list[str] = [
        "PAYPAL-AUTH-ALGO",
        "PAYPAL-CERT-URL",
        "PAYPAL-TRANSMISSION-ID",
        "PAYPAL-TRANSMISSION-SIG",
        "PAYPAL-TRANSMISSION-TIME",
    ]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Process verified PayPal webhook events.

        Events handled:
            - CHECKOUT.ORDER.APPROVED: Authorizes the draft pact and locks funds.
            - PAYMENT.AUTHORIZATION.VOIDED: Marks the pact as VOIDED if cancelled externally.
        """
        # 1. Read and validate raw transmission headers
        extracted_headers: dict[str, str] = {}
        for header_name in self.REQUIRED_HEADERS:
            header_val = request.headers.get(header_name)
            if not header_val:
                logger.warning("PayPal webhook missing required header: %s", header_name)
                return Response(
                    {"error": f"Missing required PayPal signature header: {header_name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            extracted_headers[header_name] = header_val

        # 2. Extract raw request body for verification
        try:
            raw_body: str = (
                request.body.decode("utf-8")
                if isinstance(request.body, (bytes, bytearray))
                else (request.body or json.dumps(request.data))
            )
        except Exception as exc:
            logger.exception("Failed to decode raw webhook body: %s", exc)
            return Response(
                {"error": "Failed to decode request body."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Cryptographic signature verification
        webhook_id: str = getattr(settings, "PAYPAL_WEBHOOK_ID", "")
        paypal_service: PayPalService = PayPalService()

        is_valid: bool = paypal_service.verify_webhook_signature(
            headers=extracted_headers,
            raw_body=raw_body,
            webhook_id=webhook_id,
        )

        if not is_valid:
            logger.warning(
                "PayPal webhook signature verification failed for transmission: %s",
                extracted_headers.get("PAYPAL-TRANSMISSION-ID"),
            )
            return Response(
                {"error": "Invalid webhook signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. Parse event payload
        event_payload: dict[str, Any] = request.data if isinstance(request.data, dict) else {}
        event_type: str | None = event_payload.get("event_type")
        resource: dict[str, Any] = event_payload.get("resource", {})

        logger.info("Processing verified PayPal webhook event: %s (ID: %s)", event_type, event_payload.get("id"))

        if event_type == "CHECKOUT.ORDER.APPROVED":
            self._handle_order_approved(resource, event_payload, paypal_service)
        elif event_type == "PAYMENT.AUTHORIZATION.VOIDED":
            self._handle_authorization_voided(resource, event_payload)
        else:
            logger.info("Ignoring unhandled PayPal webhook event type: %s", event_type)

        return Response({"status": "acknowledged"}, status=status.HTTP_200_OK)
    def _handle_order_approved(self, resource: dict, event_payload: dict, paypal_service: PayPalService):
        """Handle background authorization confirmations if the frontend disconnected."""
        order_id = resource.get("id")
        try:
            pact = Pact.objects.get(paypal_order_id=order_id)
            if pact.state == "DRAFT":  # Changed from status
                auth_data = paypal_service.authorize_order(order_id)
                auth_id = auth_data["purchase_units"][0]["payments"]["authorizations"][0]["id"]
                
                pact.state = "AUTHORIZED"  # Changed from status
                pact.paypal_authorization_id = auth_id
                pact.save(update_fields=["state", "paypal_authorization_id"])  # Changed from status
                
                from escrow.models import PactLedger
                PactLedger.objects.create(
                    pact=pact,
                    action="AUTHORIZED_VIA_WEBHOOK",
                    details={"paypal_authorization_id": auth_id}
                )
        except Pact.DoesNotExist:
            logger.warning(f"Webhook received for unknown order: {order_id}")
    def _handle_authorization_voided(self, resource: dict, event_payload: dict):
        """Update contract state if the authorization is voided externally or expires."""
        auth_id = resource.get("id")
        try:
            pact = Pact.objects.get(paypal_authorization_id=auth_id)
            if pact.state not in ["VOIDED", "REJECTED"]:  # Changed from status
                pact.state = "VOIDED"  # Changed from status
                pact.save(update_fields=["state"])  # Changed from status
                
                from escrow.models import PactLedger
                PactLedger.objects.create(
                    pact=pact,
                    action="FUNDS_VOIDED_EXTERNALLY",
                    details={"reason": "PayPal notification received for voided authorization"}
                )
        except Pact.DoesNotExist:
            pass
