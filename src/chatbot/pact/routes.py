"""Public PACT endpoints. The Provider fetches our keys from here to verify every request."""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Response

from ..config import settings
from .keys import PactNotConfigured, get_pact_key, pact_enabled

router = APIRouter()

CLIENT_METADATA_PATH = "/pact/client.json"
DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


def client_metadata_url() -> str:
    """Built from configuration, never from the Host header: it must equal the client_id exactly."""
    return f"{settings.chatbot_base_url.rstrip('/')}{CLIENT_METADATA_PATH}"


def client_metadata() -> Dict[str, Any]:
    """OAuth Client ID Metadata Document (draft-ietf-oauth-client-id-metadata-document).

    Describes this assistant as an OAuth client so an authorization server can register it by URL.
    Public information only: no secrets, and no private key material (the key lives in SSM).
    The client authenticates with private_key_jwt using the keys at jwks_uri.
    """
    return {
        "client_id": client_metadata_url(),
        "client_name": "Shopping Assistant",
        "jwks_uri": f"{settings.chatbot_base_url.rstrip('/')}/.well-known/jwks.json",
        "token_endpoint_auth_method": "private_key_jwt",
        "token_endpoint_auth_signing_alg": "ES256",
        "grant_types": [DEVICE_CODE_GRANT, "refresh_token"],
    }


@router.get("/.well-known/jwks.json")
async def jwks(response: Response):
    """Public key only. Cached 5 minutes; rotate by publishing the new key alongside the old."""
    if not pact_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        key = get_pact_key()
    except PactNotConfigured:
        raise HTTPException(status_code=404, detail="Not Found")
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"keys": [key.public_jwk]}


@router.get(CLIENT_METADATA_PATH)
async def client_id_metadata_document(response: Response):
    """The document an authorization server fetches for client_id == this URL (must be a plain 200)."""
    if not pact_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    response.headers["Cache-Control"] = "public, max-age=300"
    return client_metadata()
