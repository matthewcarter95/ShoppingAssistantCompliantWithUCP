"""Checkout workflow service."""
from typing import Dict, Any, List, Optional

from ..ucp.client import UCPClient
from ..conversation.state import ConversationState
from ..utils.logger import setup_logger
from ..config import settings

logger = setup_logger(__name__, settings.log_level)


class CheckoutService:
    """Service for managing checkout sessions via UCP."""

    def __init__(self, ucp_client: UCPClient):
        """
        Initialize checkout service.

        Args:
            ucp_client: UCP client instance
        """
        self.ucp_client = ucp_client

    async def start_checkout(
        self, state: ConversationState, line_items: List[Dict[str, Any]], merchant_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new checkout session.

        Args:
            state: Conversation state
            line_items: List of line items in UCP format
            merchant_token: Optional merchant access token for authorization

        Returns:
            Checkout session response
        """
        # Build UCP checkout payload
        payload = {
            "line_items": line_items,
            "currency": "USD",
            "payment": {
                "handlers": ["mock_payment_handler"]
            }
        }

        if state.buyer_info:
            payload["buyer"] = state.buyer_info

        response = await self.ucp_client.create_checkout_with_payload(payload, merchant_token)
        state.checkout_id = response.get("id")
        state.line_items = line_items
        state.status = "shopping"

        logger.info(f"Created checkout {state.checkout_id}")
        return response

    async def add_item(
        self,
        state: ConversationState,
        product_id: str,
        quantity: int = 1,
        product_info: Optional[Dict[str, Any]] = None,
        merchant_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add an item to the checkout session.

        Args:
            state: Conversation state
            product_id: Product identifier
            quantity: Quantity to add
            product_info: Optional product information for line item

        Returns:
            Updated checkout session response
        """
        if quantity < 1:
            raise ValueError("Quantity must be at least 1")

        # If no checkout exists, create one
        if not state.checkout_id:
            return await self.start_checkout(
                state, [self._new_line_item(product_id, quantity)], merchant_token
            )

        current = await self.ucp_client.get_checkout(state.checkout_id, merchant_token)

        # A finished checkout cannot take more items: start a fresh cart
        if current.get("status") in ("completed", "canceled"):
            logger.info(f"Checkout {state.checkout_id} is {current['status']}; starting a new one")
            state.checkout_id = None
            state.line_items = []
            return await self.start_checkout(
                state, [self._new_line_item(product_id, quantity)], merchant_token
            )

        line_items = self.merge_line_item(current.get("line_items", []), product_id, quantity)

        payload = self._replace_body(current)
        payload["line_items"] = line_items

        response = await self.ucp_client.update_checkout(
            state.checkout_id, payload, merchant_token
        )

        state.line_items = line_items
        logger.info(f"Added {quantity}x {product_id} to checkout {state.checkout_id}")
        return response

    @staticmethod
    def _new_line_item(product_id: str, quantity: int) -> Dict[str, Any]:
        """A line item as the merchant expects it in a request."""
        return {"item": {"id": product_id}, "quantity": quantity}

    @staticmethod
    def merge_line_item(
        existing: List[Dict[str, Any]], product_id: str, quantity: int
    ) -> List[Dict[str, Any]]:
        """
        Add `quantity` of a product to a checkout's line items.

        A product already in the cart has its quantity increased, so adding
        sunflowers twice gives one line of 2, not two lines of 1. Existing lines
        keep their ids, because a PUT replaces the whole cart. Only
        request-valid fields are sent (item title, price and totals are
        response-only).
        """
        merged: List[Dict[str, Any]] = []
        found = False
        for line in existing:
            entry: Dict[str, Any] = {
                "item": {"id": line["item"]["id"]},
                "quantity": line.get("quantity", 1),
            }
            if line.get("id"):
                entry["id"] = line["id"]
            if line["item"]["id"] == product_id and not found:
                entry["quantity"] += quantity
                found = True
            merged.append(entry)
        if not found:
            merged.append(CheckoutService._new_line_item(product_id, quantity))
        return merged

    async def update_item_quantity(
        self,
        state: ConversationState,
        product_id: str,
        new_quantity: int,
        merchant_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update the quantity of an existing item in the cart.

        Args:
            state: Conversation state
            product_id: Product identifier to update
            new_quantity: New quantity (0 to remove item)

        Returns:
            Updated checkout session response
        """
        if not state.checkout_id:
            raise ValueError("No active checkout session")

        # Get current checkout
        current_checkout = await self.ucp_client.get_checkout(state.checkout_id, merchant_token)
        existing_items = current_checkout.get("line_items", [])

        # Find and update the item
        found = False
        updated_items = []
        for item in existing_items:
            if item.get("item", {}).get("id") == product_id:
                found = True
                if new_quantity > 0:
                    item["quantity"] = new_quantity
                    updated_items.append(item)
                # If quantity is 0, don't add to updated_items (removes it)
            else:
                updated_items.append(item)

        if not found:
            raise ValueError(f"Product {product_id} not found in cart")

        # Update checkout with new line items
        update_payload = {
            "id": state.checkout_id,
            "line_items": updated_items,
            "currency": current_checkout.get("currency", "USD"),
            "payment": current_checkout.get("payment", {"handlers": ["mock_payment_handler"]}),
        }

        if current_checkout.get("discounts"):
            update_payload["discounts"] = current_checkout["discounts"]

        response = await self.ucp_client.update_checkout(
            state.checkout_id, update_payload, merchant_token
        )

        state.line_items = updated_items
        logger.info(f"Updated {product_id} quantity to {new_quantity}")
        return response

    async def remove_item(
        self,
        state: ConversationState,
        product_id: str,
        merchant_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Remove an item from the cart.

        Args:
            state: Conversation state
            product_id: Product identifier to remove

        Returns:
            Updated checkout session response
        """
        # Use update_item_quantity with quantity=0 to remove
        return await self.update_item_quantity(state, product_id, 0, merchant_token)

    async def get_cart(
        self, state: ConversationState, merchant_token: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get current cart contents.

        Args:
            state: Conversation state

        Returns:
            Cart summary with line items and totals, or None if no cart
        """
        if not state.checkout_id:
            return None

        return await self.get_checkout_summary(state, merchant_token)

    async def apply_discount(
        self, state: ConversationState, code: str, merchant_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Apply a discount code to the checkout.

        Args:
            state: Conversation state
            code: Discount code
            merchant_token: Optional merchant access token for authorization

        Returns:
            Updated checkout session response
        """
        if not state.checkout_id:
            raise ValueError("No active checkout session")

        # Get current checkout to preserve state
        current_checkout = await self.ucp_client.get_checkout(
            state.checkout_id,
            merchant_token=merchant_token
        )

        # Build full update payload
        update_payload = {
            "id": state.checkout_id,
            "line_items": current_checkout.get("line_items", state.line_items),
            "currency": current_checkout.get("currency", "USD"),
            "payment": current_checkout.get("payment", {"handlers": ["mock_payment_handler"]}),
            "discounts": {
                "codes": [code]
            }
        }

        response = await self.ucp_client.update_checkout(
            state.checkout_id, update_payload, merchant_token=merchant_token
        )

        logger.info(f"Applied discount code {code} to checkout {state.checkout_id}")
        return response

    async def setup_fulfillment(
        self,
        state: ConversationState,
        shipping_address: Dict[str, Any],
        merchant_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Set the shipping destination, then select the first offered option.

        UCP 2026-08-25 fulfillment: a method needs `id` and `line_item_ids`;
        a destination needs `id` and `type` and carries a flat postal address.
        Options are offered on `groups[]` and chosen with `selected_option_id`.

        Args:
            state: Conversation state
            shipping_address: Flat postal address (street_address, address_locality,
                address_region, postal_code, address_country)
            merchant_token: Optional merchant access token

        Returns:
            Checkout response with a shipping option selected

        Raises:
            ValueError: no checkout, or the merchant offered no shipping option
        """
        if not state.checkout_id:
            raise ValueError("No active checkout session")

        current = await self.ucp_client.get_checkout(state.checkout_id, merchant_token)
        line_item_ids = [li["id"] for li in current.get("line_items", []) if li.get("id")]
        if not line_item_ids:
            raise ValueError("Checkout has no line items to fulfill")

        destination_id = "dest_1"
        payload = self._replace_body(current)
        payload["fulfillment"] = {
            "methods": [
                {
                    "id": "method_1",
                    "type": "shipping",
                    "line_item_ids": line_item_ids,
                    "destinations": [
                        {"id": destination_id, "type": "shipping", **shipping_address}
                    ],
                    "selected_destination_id": destination_id,
                }
            ]
        }

        response = await self.ucp_client.update_checkout(
            state.checkout_id, payload, merchant_token
        )
        logger.info("Set fulfillment destination")

        # Select the first offered option on every group that has one
        fulfillment = response.get("fulfillment") or {}
        selected = None
        for method in fulfillment.get("methods", []):
            for group in method.get("groups", []):
                options = group.get("options", [])
                if options:
                    group["selected_option_id"] = options[0]["id"]
                    selected = options[0]["id"]

        if selected is None:
            raise ValueError("The merchant offered no shipping options for this address")

        selection = self._replace_body(response)
        selection["fulfillment"] = fulfillment
        result = await self.ucp_client.update_checkout(
            state.checkout_id, selection, merchant_token
        )
        logger.info(f"Selected fulfillment option {selected}")
        return result

    @staticmethod
    def _replace_body(checkout: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a full-replacement PUT body from a checkout response.

        PUT replaces the session, so everything worth keeping must be resent.
        Only fields the spec allows in a request are copied; response-only
        fields (totals, links, status, ucp, ...) are dropped.
        """
        body: Dict[str, Any] = {
            "id": checkout["id"],
            "line_items": checkout.get("line_items", []),
            "currency": checkout.get("currency", "USD"),
        }
        for key in ("buyer", "discounts", "payment", "context"):
            if checkout.get(key):
                body[key] = checkout[key]
        return body

    async def get_checkout_summary(self, state: ConversationState, merchant_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get current checkout summary.

        Args:
            state: Conversation state
            merchant_token: Optional merchant access token for authorization

        Returns:
            Checkout summary with items and totals
        """
        if not state.checkout_id:
            return None

        try:
            checkout = await self.ucp_client.get_checkout(state.checkout_id, merchant_token)

            # Parse line items from UCP format
            line_items = []
            for item in checkout.get("line_items", []):
                line_items.append({
                    "name": item.get("item", {}).get("title", item.get("item", {}).get("id", "Unknown")),
                    "product_id": item.get("item", {}).get("id"),
                    "quantity": item.get("quantity", 1),
                    "price": item.get("item", {}).get("price", 0) / 100.0,  # Convert cents to dollars
                })

            # Parse total from UCP format (in cents)
            totals = checkout.get("totals", [])
            total_amount = 0
            for total in totals:
                if total.get("type") == "total":
                    total_amount = total.get("amount", 0) / 100.0  # Convert cents to dollars
                    break

            return {
                "checkout_id": state.checkout_id,
                "line_items": line_items,
                "total": {
                    "amount": f"{total_amount:.2f}",
                    "currency": checkout.get("currency", "USD")
                },
                "status": checkout.get("status", "active"),
            }
        except Exception as e:
            logger.error(f"Failed to get checkout summary: {e}")
            return None
