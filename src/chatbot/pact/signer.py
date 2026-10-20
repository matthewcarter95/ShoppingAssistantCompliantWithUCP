"""PACT personal-agent JWT (spec §3.2) and opaque user ids (spec §3.2 `sub`)."""
import base64
import hashlib
import hmac
import time
import uuid
from typing import Optional

from jose import jwt

from ..config import settings
from .keys import PactKey, get_pact_key, read_secret

MAX_TTL_SECONDS = 300  # spec: exp at most 300 s after iat


def sign_pact_jwt(sub: str, audience: str, *, ttl_seconds: int = 120, key: Optional[PactKey] = None,
                  issuer: Optional[str] = None, now: Optional[int] = None) -> str:
    """One JWT per request: ES256, `iss` = our issuer, `aud` = the Provider's assigned audience."""
    if not 0 < ttl_seconds <= MAX_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must be between 1 and {MAX_TTL_SECONDS}")
    if not sub or not audience:
        raise ValueError("sub and audience are required")
    key = key or get_pact_key()
    iat = int(time.time()) if now is None else now
    claims = {
        "iss": issuer or settings.pact_issuer_url,
        "sub": sub,
        "aud": audience,
        "iat": iat,
        "exp": iat + ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, key.private_jwk, algorithm="ES256", headers={"kid": key.kid, "typ": "JWT"})


_cached_sub_secret: Optional[str] = None


def _sub_secret() -> str:
    global _cached_sub_secret
    if _cached_sub_secret is None:
        secret = read_secret(settings.pact_sub_secret, settings.pact_sub_secret_ssm_parameter)
        if not secret:
            raise RuntimeError("Set PACT_SUB_SECRET_SSM_PARAMETER (or PACT_SUB_SECRET for local dev)")
        _cached_sub_secret = secret
    return _cached_sub_secret


def opaque_sub(auth0_sub: str, secret: Optional[str] = None) -> str:
    """Stable, opaque id for a User. The spec forbids personal data in `sub`, and our
    own user_id is an email, so derive it: HMAC-SHA256 of the Auth0 subject under a server
    secret. Same user, same value; not reversible, and not linkable across deployments."""
    if not auth0_sub:
        raise ValueError("auth0_sub is required")
    digest = hmac.new((secret or _sub_secret()).encode(), auth0_sub.encode(), hashlib.sha256).digest()
    return "u_" + base64.urlsafe_b64encode(digest[:18]).rstrip(b"=").decode()
