"""URL routing for escrow endpoints."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import PactViewSet, PayPalWebhookView

router = DefaultRouter()
router.register(r"pacts", PactViewSet, basename="pact")

urlpatterns = [
    path("webhooks/paypal/", PayPalWebhookView.as_view(), name="paypal-webhook"),
] + router.urls
