"""Signing key for PACT personal-agent JWTs.

The private ES256 JWK lives in an SSM SecureString parameter (Lambda has no
persistent disk, and a plain env var would show the key in the console). It is
read once per container. The public half is served as a JWKS.
"""
import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from ..config import settings


class PactNotConfigured(RuntimeError):
    """PACT is off: no key is configured."""


@dataclass(frozen=True)
class PactKey:
    private_jwk: Dict[str, str]  # includes `d`; never serialised outside this process
    kid: str

    @property
    def public_jwk(self) -> Dict[str, str]:
        return {
            "kty": "EC",
            "crv": "P-256",
            "x": self.private_jwk["x"],
            "y": self.private_jwk["y"],
            "kid": self.kid,
            "alg": "ES256",
            "use": "sig",
        }


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def thumbprint(jwk: Dict[str, str]) -> str:
    """RFC 7638 SHA-256 thumbprint of an EC public key; used as `kid`."""
    members = {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]}
    canonical = json.dumps(members, separators=(",", ":"), sort_keys=True)
    return _b64url(hashlib.sha256(canonical.encode()).digest())


def parse_private_jwk(raw: str) -> PactKey:
    jwk = json.loads(raw)
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or not all(jwk.get(k) for k in ("d", "x", "y")):
        raise ValueError("PACT key must be a private EC P-256 JWK")
    return PactKey(private_jwk=jwk, kid=thumbprint(jwk))


def _read_ssm(name: str) -> str:
    import boto3  # imported lazily: local runs and tests don't need AWS

    client = boto3.client("ssm", region_name=settings.aws_region)
    return client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


def read_secret(direct: str, ssm_parameter: str, reader: Callable[[str], str] = _read_ssm) -> Optional[str]:
    """Direct value (local dev) wins; otherwise the SSM SecureString; otherwise None."""
    if direct:
        return direct
    if ssm_parameter:
        return reader(ssm_parameter)
    return None


_cached_key: Optional[PactKey] = None


def get_pact_key() -> PactKey:
    global _cached_key
    if _cached_key is None:
        raw = read_secret(settings.pact_private_jwk, settings.pact_key_ssm_parameter)
        if not raw:
            raise PactNotConfigured("Set PACT_KEY_SSM_PARAMETER (or PACT_PRIVATE_JWK for local dev)")
        _cached_key = parse_private_jwk(raw)
    return _cached_key


def pact_enabled() -> bool:
    return bool(settings.pact_private_jwk or settings.pact_key_ssm_parameter)
