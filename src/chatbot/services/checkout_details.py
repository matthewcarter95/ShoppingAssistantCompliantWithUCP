"""Decide which buyer details may be used to place an order.

Two sources are acceptable, and nothing else:

1. Details the shopper typed themselves in this conversation.
2. Details from the merchant access token (name, email, shipping address),
   but only after the assistant has shown them and the shopper said yes.

Anything the model supplies that matches neither is rejected, so it cannot
invent or paraphrase order details.
"""
import re
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
    since: int = 0,
) -> DetailsDecision:
    """
    Pick the details to order with, or say what is still needed.

    Args:
        messages: conversation Message objects, oldest first
        arguments: what the model passed to complete_order (untrusted)
        token_profile: details from the merchant token, if it carried them
        parse_address: turns a typed address line into a UCP flat address
        since: index in `messages` where the current checkout conversation
            starts. Details the shopper typed earlier still count; a saved-details
            confirmation only counts if it happened at or after this point.
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
    scoped = messages[since:]
    if details_confirmed(scoped, token_profile):
        return DetailsDecision(
            READY,
            buyer_info=token_profile.as_buyer_info(),
            address=dict(token_profile.address),
            source="token",
        )

    # 4. Saved details were shown and the shopper replied with something other
    #    than a plain yes: they want changes, so collect details by typing.
    shown = confirmation_shown_index(scoped, token_profile)
    if shown >= 0 and any(m.role == "user" for m in scoped[shown + 1:]):
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


STAGE_DETAILS = "details"
STAGE_CARD = "card"
STAGE_POINTS = "points"
OPEN_QUESTION_STAGES = (STAGE_DETAILS, STAGE_CARD, STAGE_POINTS)

_CHECKOUT_INTENT = re.compile(
    r"\b(check\s?out|complete[_ ]?(my |the |this )?order|place (my |the |this |an? )?order|"
    r"buy (it )?now|pay now|proceed to (check\s?out|payment))\b",
    re.IGNORECASE,
)
_OTHER_INTENT = re.compile(
    r"\b(add|remove|delete|search|show|find|cancel|never\s?mind|stop|view|what)\b", re.IGNORECASE
)


def wants_checkout(message: str) -> bool:
    """True if the shopper's message asks to check out."""
    return bool(_CHECKOUT_INTENT.search(message or ""))


def should_force_complete_order(message: str, has_checkout: bool, stage: Optional[str]) -> bool:
    """
    Whether the next model call must be `complete_order`.

    Forced when the shopper asks to check out, and while a question we asked
    (saved details, loyalty points) is waiting for their reply, unless the
    reply is clearly about something else. This keeps the checkout sequence
    under server control instead of depending on the model choosing the tool.
    """
    if not has_checkout:
        return False
    if wants_checkout(message):
        return True
    if stage in OPEN_QUESTION_STAGES:
        # A reply to our question is short; a long message is a new request.
        return len((message or "").split()) <= 25 and not _OTHER_INTENT.search(message or "")
    return False


def points_offer(max_redeem_percent: Optional[int], currency_name: Optional[str] = None) -> str:
    """The question shown to loyalty members at every checkout."""
    cap = f" They can cover up to {max_redeem_percent}% of the order." if max_redeem_percent else ""
    name = f" ({currency_name})" if currency_name else ""
    return (
        f"You have loyalty points{name} with this merchant. Would you like to pay part of this "
        f"order with them?{cap} Reply \"no\", \"as many as allowed\", or a dollar amount such as \"$5\"."
    )
