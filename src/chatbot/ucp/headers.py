"""UCP header generation utilities."""
import uuid
from typing import Dict


def generate_ucp_headers(agent_profile: str) -> Dict[str, str]:
    """
    Generate required UCP headers for API requests.

    Args:
        agent_profile: The UCP agent profile URL

    Returns:
        Dictionary of required UCP headers
    """
    return {
        "UCP-Agent": f'profile="{agent_profile}"',
        "request-signature": "chatbot-request",
        "idempotency-key": str(uuid.uuid4()),
        "request-id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
