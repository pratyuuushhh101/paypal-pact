"""Custom permission classes governing access control for Pact escrow lifecycle operations."""

from typing import Any
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from .models import Pact


class IsPactBuyer(BasePermission):
    """Only the buyer of the pact can perform this action."""

    def has_object_permission(self, request: Request, view: APIView, obj: Pact) -> bool:
        """Check if the requesting user is the designated buyer of the pact."""
        return obj.buyer == request.user


class IsPactParty(BasePermission):
    """Only a buyer or seller of the pact can access it."""

    def has_object_permission(self, request: Request, view: APIView, obj: Pact) -> bool:
        """Check if the requesting user is either the buyer or the seller of the pact."""
        return request.user in [obj.buyer, obj.seller]


class IsPactSellerOrUnassigned(BasePermission):
    """Only the assigned seller can submit. If no seller is assigned, allow any authenticated user."""

    def has_object_permission(self, request: Request, view: APIView, obj: Pact) -> bool:
        """Check if the user is the assigned seller or if the pact is open for any seller."""
        if obj.seller is None:
            return True
        return obj.seller == request.user
