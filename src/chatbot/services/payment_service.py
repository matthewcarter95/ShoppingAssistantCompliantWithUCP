"""Payment processing service."""
from dataclasses import dataclass
from typing import Dict, Any, Optional

from ..ucp.client import UCPClient
from ..ucp.profile import LOYALTY_HANDLER_ID, SPLIT_PAYMENTS_CAPABILITY
from .checkout_payment import SavedCard
from ..conversation.state import ConversationState
from ..utils.logger import setup_logger
from ..config import settings

logger = setup_logger(__name__, settings.log_level)

POINTS_INSTRUMENT_ID = "pts_1"


@dataclass(frozen=True)
class PointsRequest:
    """A shopper's request to pay with loyalty points."""

    # Minor units (cents) of the order currency. None = open amount: the
    # merchant spends as many points as the balance and its cap allow.
    amount_cents: Optional[int] = None


def check_points_amount(amount_cents: int, total_cents: int, config: Dict[str, Any]) -> None:
    """
    Validate an explicit points amount against the merchant's published rules.

    `config` is the loyalty handler's `config` from the merchant profile
    (`cents_per_point`, `max_redeem_percent`). Raises ValueError with text
    that is safe to show the shopper.
    """
    if amount_cents <= 0:
        raise ValueError("The points amount must be more than $0.")
    cents_per_point = int(config.get("cents_per_point") or 1)
    if amount_cents % cents_per_point:
        raise ValueError(
            f"Points can only be spent in multiples of {cents_per_point} cent(s)."
        )
    if amount_cents > total_cents:
        raise ValueError(
            f"That is more than the order total of ${total_cents / 100:.2f}."
        )
    percent = config.get("max_redeem_percent")
    if percent is not None:
        cap = total_cents * int(percent) // 100
        if amount_cents > cap:
            raise ValueError(
                f"Points can cover at most {percent}% of an order "
                f"(${cap / 100:.2f} of ${total_cents / 100:.2f})."
            )


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
        self,
        state: ConversationState,
        buyer_info: Dict[str, Any],
        merchant_token: Optional[str] = None,
        points: Optional[PointsRequest] = None,
        address: Optional[Dict[str, str]] = None,
        card: Optional[SavedCard] = None,
    ) -> Dict[str, Any]:
        """
        Complete checkout with mock payment, optionally paying part in points.

        Args:
            state: Conversation state
            buyer_info: Dictionary with buyer_name, buyer_email, shipping_address
            merchant_token: Merchant access token (needs the `complete` scope)
            points: If set, spend loyalty points as a split payment; the card
                covers the remainder
            address: Already-structured UCP postal address to use as the billing
                address. When omitted, buyer_info["shipping_address"] is parsed.
            card: A card the merchant has saved for this buyer. Only its id is
                sent; the merchant supplies the credential. When omitted, the
                mock test card is used.

        Returns:
            Order completion response

        Raises:
            ValueError: points requested but unavailable or out of bounds
        """
        if not state.checkout_id:
            raise ValueError("No active checkout session")

        # Billing address for the mock card: the shipping address
        shipping_address = address or self._parse_address(buyer_info["shipping_address"])

        # UCP 2026-08-25: payment.instruments[], each tied to a handler by id.
        # The mock handler accepts "success_token"; "fail_token" simulates a decline.
        if card is not None:
            instrument = {"id": card.id, "handler_id": card.handler_id, "type": "card"}
        else:
            instrument = {
                "id": "card_1",
                "handler_id": "mock_payment_handler",
                "type": "card",
                "credential": {"type": "token", "token": "success_token"},
                "billing_address": shipping_address,
            }
        instruments = [instrument]

        if points is not None:
            instruments = [
                await self._points_instrument(state, points, merchant_token),
                instrument,
            ]

        # `risk_signals` is not in the 2026-08-25 spec, but the merchant still
        # rejects complete without it (422 "Field required at risk_signals").
        # Remove once the merchant drops the requirement.
        complete_payload = {
            "payment": {"instruments": instruments},
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

    async def _points_instrument(
        self,
        state: ConversationState,
        points: PointsRequest,
        merchant_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Build the loyalty-points instrument for a split payment.

        With an explicit amount, it is checked against the program's rules
        before the merchant is called. Without one (open amount), the merchant
        applies min(balance, cap).
        """
        profile = await self.ucp_client.get_profile()
        handler = profile.handler_by_id(LOYALTY_HANDLER_ID)
        if not handler or not await self.ucp_client.has_capability(SPLIT_PAYMENTS_CAPABILITY):
            raise ValueError("This merchant does not accept loyalty points.")

        instrument: Dict[str, Any] = {
            "id": POINTS_INSTRUMENT_ID,
            "handler_id": LOYALTY_HANDLER_ID,
            "type": "loyalty",
            "credential": {"type": "loyalty", "token": "ignored"},
        }
        if points.amount_cents is not None:
            checkout = await self.ucp_client.get_checkout(state.checkout_id, merchant_token)
            total = next(
                (t["amount"] for t in checkout.get("totals", []) if t.get("type") == "total"),
                None,
            )
            if total is None:
                raise ValueError("Could not read the order total from the merchant.")
            check_points_amount(points.amount_cents, total, handler.get("config") or {})
            instrument["amount"] = points.amount_cents
        return instrument

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
