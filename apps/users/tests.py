"""Unit and integration tests for authentication endpoints and user serializers."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import PactUser


class AuthEndpointTests(APITestCase):
    """Test suite for user registration, JWT login, token refresh, and profile endpoints."""

    def setUp(self) -> None:
        """Initialize test URLs and shared test fixtures."""
        self.register_url: str = reverse("auth-register")
        self.login_url: str = reverse("auth-login")
        self.refresh_url: str = reverse("auth-refresh")
        self.profile_url: str = reverse("auth-profile")
        self.pact_create_url: str = reverse("pact-create-pact")

        self.test_email: str = "testuser@example.com"
        self.test_password: str = "SecurePass123!"

    def test_register_success(self) -> None:
        """Ensure a user can register and receive user details along with JWT token pair."""
        payload = {
            "email": "newuser@example.com",
            "password": "Password123!",
            "password_confirm": "Password123!",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("user", response.data)
        self.assertIn("tokens", response.data)
        self.assertEqual(response.data["user"]["email"], "newuser@example.com")
        self.assertIn("access", response.data["tokens"])
        self.assertIn("refresh", response.data["tokens"])
        self.assertTrue(PactUser.objects.filter(email="newuser@example.com").exists())

    def test_register_duplicate_email(self) -> None:
        """Ensure registering with an already existing email returns HTTP 400."""
        PactUser.objects.create_user(email=self.test_email, password=self.test_password)
        payload = {
            "email": self.test_email,
            "password": "Password123!",
            "password_confirm": "Password123!",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_password_mismatch(self) -> None:
        """Ensure mismatched passwords during registration trigger a validation error."""
        payload = {
            "email": "mismatch@example.com",
            "password": "Password123!",
            "password_confirm": "DifferentPassword123!",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data)

    def test_login_success(self) -> None:
        """Ensure existing user can authenticate with credentials and receive JWT tokens."""
        PactUser.objects.create_user(email=self.test_email, password=self.test_password)
        payload = {
            "email": self.test_email,
            "password": self.test_password,
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_wrong_password(self) -> None:
        """Ensure invalid password credentials return HTTP 401 Unauthorized."""
        PactUser.objects.create_user(email=self.test_email, password=self.test_password)
        payload = {
            "email": self.test_email,
            "password": "WrongPassword123!",
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_refresh(self) -> None:
        """Ensure a valid refresh token can obtain a new access token."""
        PactUser.objects.create_user(email=self.test_email, password=self.test_password)
        login_res = self.client.post(
            self.login_url,
            {"email": self.test_email, "password": self.test_password},
            format="json",
        )
        refresh_token = login_res.data["refresh"]

        refresh_res = self.client.post(
            self.refresh_url,
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertIn("access", refresh_res.data)

    def test_profile_authenticated(self) -> None:
        """Ensure authenticated user with Bearer token can access their profile."""
        PactUser.objects.create_user(email=self.test_email, password=self.test_password)
        login_res = self.client.post(
            self.login_url,
            {"email": self.test_email, "password": self.test_password},
            format="json",
        )
        access_token = login_res.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.test_email)

    def test_profile_unauthenticated(self) -> None:
        """Ensure unauthenticated access to profile returns HTTP 401 Unauthorized."""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_pact_create_requires_auth(self) -> None:
        """Ensure attempting to create a pact without JWT authentication returns HTTP 401 Unauthorized."""
        payload = {
            "amount": "150.00",
            "currency": "USD",
            "deliverable_type": "JSON_DATASET",
        }
        response = self.client.post(self.pact_create_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
