"""JWT token validation for shopping assistant Auth0."""

import json
from typing import Dict, Optional
from urllib.request import urlopen

from jose import jwt, JWTError
from .config import auth0_settings


class JWTValidator:
    """Validates JWT tokens from shopping assistant Auth0."""

    def __init__(self):
        self.domain = auth0_settings.shopping_assistant_auth0_domain
        self.algorithms = auth0_settings.shopping_assistant_auth0_algorithms
        self._jwks_cache: Optional[Dict] = None

    def _get_jwks(self) -> Dict:
        """Fetch JWKS from Auth0 (cached)."""
        if self._jwks_cache is None:
            jwks_url = f"https://{self.domain}/.well-known/jwks.json"
            with urlopen(jwks_url) as response:
                self._jwks_cache = json.loads(response.read())
        return self._jwks_cache

    def _get_signing_key(self, token: str) -> str:
        """Extract signing key from JWKS for given token."""
        jwks = self._get_jwks()
        unverified_header = jwt.get_unverified_header(token)

        # Check if kid exists in header
        if "kid" not in unverified_header:
            raise ValueError("Token header missing 'kid' field")

        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
                break

        if not rsa_key:
            raise ValueError(f"Unable to find signing key for kid: {unverified_header['kid']}")

        return json.dumps(rsa_key)

    def validate_token(self, token: str) -> Dict:
        """
        Validate JWT token and return claims.

        Args:
            token: JWT token string

        Returns:
            Dict with user claims (sub, email, etc.)

        Raises:
            JWTError: If token is invalid
            ValueError: If signing key not found
        """
        try:
            # Get signing key
            signing_key = self._get_signing_key(token)

            # Validate token
            # Note: No audience validation for shopping assistant
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=self.algorithms,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                }
            )

            return payload

        except JWTError as e:
            raise JWTError(f"Invalid token: {str(e)}")
        except Exception as e:
            raise ValueError(f"Token validation error: {str(e)}")


# Global validator instance
jwt_validator = JWTValidator()
