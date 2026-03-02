"""Payment processing service."""
from typing import Dict, Any

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
        self, state: ConversationState, buyer_info: Dict[str, Any]
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

        # Parse shipping address
        shipping_address = self._parse_address(buyer_info["shipping_address"])

        # Create mock payment instrument for complete endpoint
        payment_data = {
            "id": "mock_payment_123",
            "type": "card",
            "handler_id": "mock_payment_handler",
            "brand": "visa",
            "last_digits": "4242",
            "token": "success_token",
            "billing_address": {
                "type": "PostalAddress",
                "street_address": shipping_address.get("street_address", "123 Main St"),
                "address_locality": shipping_address.get("address_locality", "Anytown"),
                "address_region": shipping_address.get("address_region", "CA"),
                "address_country": shipping_address.get("address_country", "US"),
                "postal_code": shipping_address.get("postal_code", "12345"),
            },
        }

        # Risk signals (required field)
        risk_signals = {
            "ip_address": "127.0.0.1",
            "user_agent": "shopping-assistant-chatbot/1.0",
        }

        # Build complete payload
        complete_payload = {
            "payment_data": payment_data,
            "risk_signals": risk_signals,
        }

        logger.info(f"Completing checkout {state.checkout_id} with mock payment")
        response = await self.ucp_client.complete_checkout(
            state.checkout_id, complete_payload
        )

        state.status = "completed"
        logger.info(f"Order completed: {response.get('order', {}).get('id')}")
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
