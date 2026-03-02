"""Merchant OAuth Authorization Code + PKCE flow."""

import hashlib
import base64
import secrets
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from .config import auth0_settings


class MerchantOAuthClient:
    """Handles merchant OAuth authorization with PKCE."""

    def __init__(self):
        self.domain = auth0_settings.merchant_auth0_domain
        self.client_id = auth0_settings.merchant_auth0_client_id
        self.audience = auth0_settings.merchant_auth0_audience
        self.scope = auth0_settings.merchant_auth0_scope
        self.redirect_uri = auth0_settings.merchant_auth0_redirect_uri

    def generate_pkce_pair(self) -> Tuple[str, str]:
        """
        Generate PKCE code_verifier and code_challenge.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code_verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8')
        code_verifier = code_verifier.rstrip('=')  # Remove padding

        # Generate code_challenge = BASE64URL(SHA256(code_verifier))
        challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8')
        code_challenge = code_challenge.rstrip('=')  # Remove padding

        return code_verifier, code_challenge

    def generate_state(self, session_id: str, intent: str = "create") -> str:
        """
        Generate state parameter for CSRF protection.

        Format: {session_id}_{csrf_token}_{intent}

        Args:
            session_id: Session ID to track user
            intent: Intent value (check, create, get)

        Returns:
            State string
        """
        csrf_token = secrets.token_urlsafe(16)
        return f"{session_id}_{csrf_token}_{intent}"

    def parse_state(self, state: str) -> Tuple[str, str, str]:
        """
        Parse state parameter.

        Args:
            state: State string from callback

        Returns:
            Tuple of (session_id, csrf_token, intent)

        Raises:
            ValueError: If state format is invalid
        """
        parts = state.split('_')
        if len(parts) < 3:
            raise ValueError("Invalid state format")

        session_id = parts[0]
        csrf_token = parts[1]
        intent = parts[2]

        return session_id, csrf_token, intent

    def build_authorization_url(
        self,
        state: str,
        code_challenge: str,
        intent: str = "create"
    ) -> str:
        """
        Build authorization URL for merchant OAuth.

        Args:
            state: State parameter for CSRF protection
            code_challenge: PKCE code_challenge
            intent: Intent value (check, create, get)

        Returns:
            Authorization URL
        """
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "audience": self.audience,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "intent": intent,
        }

        return f"https://{self.domain}/authorize?{urlencode(params)}"

    async def exchange_code_for_token(
        self,
        authorization_code: str,
        code_verifier: str
    ) -> Dict:
        """
        Exchange authorization code for access token.

        Args:
            authorization_code: Authorization code from callback
            code_verifier: PKCE code_verifier

        Returns:
            Dict with token response:
            {
                "access_token": "...",
                "refresh_token": "...",
                "expires_in": 86400,
                "token_type": "Bearer"
            }

        Raises:
            httpx.HTTPError: If token exchange fails
        """
        token_url = f"https://{self.domain}/oauth/token"

        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": authorization_code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, json=payload)
            response.raise_for_status()
            return response.json()

    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token

        Returns:
            Dict with new token response

        Raises:
            httpx.HTTPError: If refresh fails
        """
        token_url = f"https://{self.domain}/oauth/token"

        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": refresh_token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, json=payload)
            response.raise_for_status()
            return response.json()

    def calculate_expiration(self, expires_in: int) -> str:
        """
        Calculate token expiration timestamp.

        Args:
            expires_in: Seconds until expiration

        Returns:
            ISO 8601 timestamp string
        """
        expiration = datetime.utcnow() + timedelta(seconds=expires_in)
        return expiration.isoformat() + "Z"

    def is_token_expired(self, expires_at: str) -> bool:
        """
        Check if token is expired.

        Args:
            expires_at: ISO 8601 expiration timestamp

        Returns:
            True if expired, False otherwise
        """
        expiration = datetime.fromisoformat(expires_at.rstrip('Z'))
        # Add 5 minute buffer
        return datetime.utcnow() >= (expiration - timedelta(minutes=5))


# Global client instance
merchant_oauth_client = MerchantOAuthClient()
