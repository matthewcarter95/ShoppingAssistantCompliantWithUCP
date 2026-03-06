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
        # Build line item in UCP format
        line_item = {
            "item": {
                "type": "Product",
                "id": product_id,
            },
            "quantity": quantity,
        }

        # If no checkout exists, create one
        if not state.checkout_id:
            return await self.start_checkout(state, [line_item], merchant_token)

        # Otherwise, update existing checkout - need full payload
        current_checkout = await self.ucp_client.get_checkout(state.checkout_id, merchant_token)
        existing_items = current_checkout.get("line_items", [])
        existing_items.append(line_item)

        update_payload = {
            "id": state.checkout_id,
            "line_items": existing_items,
            "currency": current_checkout.get("currency", "USD"),
            "payment": current_checkout.get("payment", {"handlers": ["mock_payment_handler"]}),
        }

        # Preserve discounts if any
        if current_checkout.get("discounts"):
            update_payload["discounts"] = current_checkout["discounts"]

        response = await self.ucp_client.update_checkout(
            state.checkout_id, update_payload, merchant_token
        )

        state.line_items = existing_items
        logger.info(f"Added {quantity}x {product_id} to checkout {state.checkout_id}")
        return response

    async def update_item_quantity(
        self,
        state: ConversationState,
        product_id: str,
        new_quantity: int,
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
        current_checkout = await self.ucp_client.get_checkout(state.checkout_id)
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
            state.checkout_id, update_payload
        )

        state.line_items = updated_items
        logger.info(f"Updated {product_id} quantity to {new_quantity}")
        return response

    async def remove_item(
        self,
        state: ConversationState,
        product_id: str,
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
        return await self.update_item_quantity(state, product_id, 0)

    async def get_cart(self, state: ConversationState) -> Optional[Dict[str, Any]]:
        """
        Get current cart contents.

        Args:
            state: Conversation state

        Returns:
            Cart summary with line items and totals, or None if no cart
        """
        if not state.checkout_id:
            return None

        return await self.get_checkout_summary(state)

    async def apply_discount(
        self, state: ConversationState, code: str
    ) -> Dict[str, Any]:
        """
        Apply a discount code to the checkout.

        Args:
            state: Conversation state
            code: Discount code

        Returns:
            Updated checkout session response
        """
        if not state.checkout_id:
            raise ValueError("No active checkout session")

        # Get current checkout to preserve state
        current_checkout = await self.ucp_client.get_checkout(state.checkout_id)

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
            state.checkout_id, update_payload
        )

        logger.info(f"Applied discount code {code} to checkout {state.checkout_id}")
        return response

    async def setup_fulfillment(
        self, state: ConversationState, shipping_address: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Setup fulfillment with shipping address and select first available option.

        Args:
            state: Conversation state
            shipping_address: Shipping address dictionary

        Returns:
            Updated checkout session with fulfillment options
        """
        if not state.checkout_id:
            raise ValueError("No active checkout session")

        # Get current checkout to build complete payload
        current_checkout = await self.ucp_client.get_checkout(state.checkout_id)

        # Step 1: Update with fulfillment.methods to trigger options
        update_payload = {
            "id": state.checkout_id,
            "line_items": current_checkout.get("line_items", []),
            "currency": current_checkout.get("currency", "USD"),
            "payment": current_checkout.get("payment", {"handlers": ["mock_payment_handler"]}),
            "fulfillment": {
                "methods": [
                    {
                        "type": "shipping",
                        "destinations": [
                            {
                                "id": "dest_1",
                                "postal_address": shipping_address,
                            }
                        ],
                    }
                ],
            }
        }

        # Preserve discounts if any
        if current_checkout.get("discounts"):
            update_payload["discounts"] = current_checkout["discounts"]

        # Preserve buyer if any
        if current_checkout.get("buyer"):
            update_payload["buyer"] = current_checkout["buyer"]

        response = await self.ucp_client.update_checkout(
            state.checkout_id,
            update_payload
        )

        logger.info("Triggered fulfillment options")

        # Step 2: Select first available option
        fulfillment = response.get("fulfillment")
        if fulfillment and isinstance(fulfillment, dict):
            # Check for options in methods (UCP format has options nested in methods/groups)
            methods = fulfillment.get("methods", [])
            if methods:
                for method in methods:
                    groups = method.get("groups", [])
                    if groups:
                        # Found groups with options, select the first one
                        first_group = groups[0]
                        options = first_group.get("options", [])
                        if options:
                            first_option = options[0]

                            # Get updated checkout and add selection
                            current = await self.ucp_client.get_checkout(state.checkout_id)
                            current_fulfillment = current.get("fulfillment", {})
                            current_methods = current_fulfillment.get("methods", [])

                            # Update the first method's first group with selected option
                            if current_methods:
                                current_methods[0]["groups"][0]["selected_option_id"] = first_option["id"]

                            selection_payload = {
                                "id": state.checkout_id,
                                "line_items": current.get("line_items", []),
                                "currency": current.get("currency", "USD"),
                                "payment": current.get("payment", {"handlers": ["mock_payment_handler"]}),
                                "fulfillment": current_fulfillment
                            }

                            if current.get("discounts"):
                                selection_payload["discounts"] = current["discounts"]
                            if current.get("buyer"):
                                selection_payload["buyer"] = current["buyer"]

                            selection_response = await self.ucp_client.update_checkout(
                                state.checkout_id,
                                selection_payload
                            )
                            logger.info(f"Selected fulfillment option {first_option['id']}")
                            return selection_response

        return response

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
