"""Decide which buyer details may be used to place an order.

Two sources are acceptable, and nothing else:

1. Details the shopper typed themselves in this conversation.
2. Details from the merchant access token (name, email, shipping address),
   but only after the assistant has shown them and the shopper said yes.

Anything the model supplies that matches neither is rejected, so it cannot
invent or paraphrase order details.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .buyer_claims import BuyerProfile
from .buyer_input import (
    confirmation_shown_index,
    details_confirmed,
    missing_address_parts,
    unverified_fields,
)

READY = "ready"      # use buyer_info / address now
CONFIRM = "confirm"  # show `message` to the shopper and wait for a reply
ASK = "ask"          # `message` is an instruction for the model (tool error)

DETAIL_FIELDS = ("buyer_name", "buyer_email", "shipping_address")


@dataclass
class DetailsDecision:
    kind: str
    buyer_info: Optional[Dict[str, str]] = None
    address: Optional[Dict[str, str]] = None
    message: Optional[str] = None
    source: Optional[str] = None  # "typed" | "token"


def confirmation_prompt(profile: BuyerProfile) -> str:
    """The text shown to the shopper. Must contain the email and street so the
    later reply can be matched to it (see buyer_input.confirmation_shown_index)."""
    return (
        "I have these details from your merchant account:\n\n"
        f"{profile.summary()}\n\n"
        'Shall I use them for this order? Reply "yes" to confirm, or tell me what to change.'
    )


def resolve_checkout_details(
    messages: List[Any],
    arguments: Dict[str, Any],
    token_profile: Optional[BuyerProfile],
    parse_address: Callable[[str], Dict[str, str]],
) -> DetailsDecision:
    """
    Pick the details to order with, or say what is still needed.

    Args:
        messages: conversation Message objects, oldest first
        arguments: what the model passed to complete_order (untrusted)
        token_profile: details from the merchant token, if it carried them
        parse_address: turns a typed address line into a UCP flat address
    """
    buyer_info = {f: str(arguments.get(f) or "") for f in DETAIL_FIELDS}
    typed = [m.content for m in messages if m.role == "user"]

    # 1. Everything the model passed was typed by the shopper.
    invented = unverified_fields(buyer_info, typed)
    if not invented:
        address = parse_address(buyer_info["shipping_address"])
        missing = missing_address_parts(address)
        if missing:
            return DetailsDecision(
                ASK,
                message=(
                    "ERROR: The shipping address is incomplete (missing "
                    + ", ".join(missing)
                    + "). Ask the user for the full address as 'street, city, STATE ZIP'."
                ),
            )
        return DetailsDecision(READY, buyer_info=buyer_info, address=address, source="typed")

    # 2. No saved details to fall back on: the shopper has to type them.
    if token_profile is None:
        names = ", ".join(f.replace("buyer_", "").replace("_", " ") for f in invented)
        return DetailsDecision(
            ASK,
            message=(
                f"ERROR: Do not guess order details. The user has not provided: {names}. "
                "Ask the user for them, then call complete_order again."
            ),
        )

    # 3. Saved details the shopper has confirmed.
    if details_confirmed(messages, token_profile):
        return DetailsDecision(
            READY,
            buyer_info=token_profile.as_buyer_info(),
            address=dict(token_profile.address),
            source="token",
        )

    # 4. Saved details were shown and the shopper replied with something other
    #    than a plain yes: they want changes, so collect details by typing.
    shown = confirmation_shown_index(messages, token_profile)
    if shown >= 0 and any(m.role == "user" for m in messages[shown + 1:]):
        return DetailsDecision(
            ASK,
            message=(
                "ERROR: The user did not accept the saved details. Ask for their full name, "
                "email and shipping address ('street, city, STATE ZIP'), then call "
                "complete_order with exactly what they type."
            ),
        )

    # 5. Show the saved details and wait.
    return DetailsDecision(CONFIRM, message=confirmation_prompt(token_profile))
