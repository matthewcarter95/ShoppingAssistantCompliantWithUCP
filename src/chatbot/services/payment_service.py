"""Payment processing service."""
from typing import Dict, Any, Optional

from ..ucp.client import UCPClient
from ..conversation.state import ConversationState
from ..utils.logger import setup_logger
from ..config import settings

logger = setup_logger(__name__, settings.log_level)


class PaymentService:
    """Service for completing payment via UCP."""

    def __init__(self, ucp_client: UCPClient):
        """
        Initialize payment service.

        Args:
            ucp_client: UCP client instance
        """
        self.ucp_client = ucp_client

    async def complete_checkout(
        self, state: ConversationState, buyer_info: Dict[str, Any], merchant_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete checkout with mock payment.

        Args:
            state: Conversation state
            buyer_info: Dictionary with buyer_name, buyer_email, shipping_address

        Returns:
            Order completion response
        """
        if not state.checkout_id:
            raise ValueError("No active checkout session")

        # Parse shipping address (used as the billing address for the mock card)
        shipping_address = self._parse_address(buyer_info["shipping_address"])

        # UCP 2026-08-25: payment.instruments[], each tied to a handler by id.
        # The mock handler accepts "success_token"; "fail_token" simulates a decline.
        instrument = {
            "id": "instr_1",
            "handler_id": "mock_payment_handler",
            "type": "card",
            "credential": {"type": "token", "token": "success_token"},
            "billing_address": shipping_address,
        }

        # `risk_signals` is not in the 2026-08-25 spec, but the merchant still
        # rejects complete without it (422 "Field required at risk_signals").
        # Remove once the merchant drops the requirement.
        complete_payload = {
            "payment": {"instruments": [instrument]},
            "risk_signals": {
                "ip_address": "127.0.0.1",
                "user_agent": "shopping-assistant-chatbot/1.0",
            },
        }

        logger.info(f"Completing checkout {state.checkout_id} with mock payment")
        response = await self.ucp_client.complete_checkout(
            state.checkout_id, complete_payload, merchant_token
        )

        # Trust the merchant's status; `complete_in_progress` is not "completed"
        state.status = response.get("status", state.status)
        logger.info(f"Checkout {state.checkout_id} is {state.status}; order {(response.get('order') or {}).get('id')}")
        return response

    def _parse_address(self, address_str: str) -> Dict[str, str]:
        """
        Parse address string into components.

        Simple parser that splits on commas and extracts components.

        Args:
            address_str: Address as string (e.g., "123 Main St, Anytown, CA 12345")

        Returns:
            Dictionary with address components
        """
        parts = [p.strip() for p in address_str.split(",")]

        result = {
            "street_address": parts[0] if len(parts) > 0 else "",
            "address_locality": parts[1] if len(parts) > 1 else "",
            "address_country": "US",
        }

        # Try to extract state and zip from last part
        if len(parts) > 2:
            last_part = parts[-1].strip()
            # Split on space to get state and zip
            tokens = last_part.split()
            if len(tokens) >= 2:
                result["address_region"] = tokens[0]
                result["postal_code"] = tokens[1]
            elif len(tokens) == 1:
                # Could be just state or just zip
                if tokens[0].isdigit():
                    result["postal_code"] = tokens[0]
                else:
                    result["address_region"] = tokens[0]

        return result
