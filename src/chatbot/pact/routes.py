"""Public PACT endpoints. The Provider fetches our keys from here to verify every request."""
from fastapi import APIRouter, HTTPException, Response

from .keys import PactNotConfigured, get_pact_key, pact_enabled

router = APIRouter()


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
