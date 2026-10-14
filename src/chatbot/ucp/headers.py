"""UCP header generation utilities (UCP 2026-08-25, REST binding)."""
import uuid
from typing import Dict, Optional


def generate_ucp_headers(
    agent_profile: str,
    *,
    idempotent: bool = False,
    idempotency_key: Optional[str] = None,
    has_body: bool = False,
) -> Dict[str, str]:
    """
    Generate UCP headers for a request.

    Args:
        agent_profile: URL of the agent's /.well-known/ucp profile
        idempotent: True for state-changing calls (POST/PUT); adds Idempotency-Key
        idempotency_key: Reuse a key when retrying the same logical operation
        has_body: True if the request carries a JSON body (adds Content-Type)

    Returns:
        Dictionary of headers. `Request-Id` is always present, `Idempotency-Key`
        only on state-changing calls, `Content-Type` only with a body.
    """
    headers = {
        "UCP-Agent": f'profile="{agent_profile}"',
        "Request-Id": str(uuid.uuid4()),
    }
    if idempotent:
        headers["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())
    if has_body:
        headers["Content-Type"] = "application/json"
    return headers
