"""Checks that order details came from the user, not from the model.

The model is told to ask for name, email and address, but nothing stops it
from inventing them. These checks run server-side before any merchant call.
"""
import re
from typing import Dict, Iterable, List

_NON_ALNUM = re.compile(r"[^a-z0-9@.]+")


def _tokens(text: str) -> List[str]:
    return [t for t in _NON_ALNUM.sub(" ", text.lower()).split() if t]


def appears_in_user_messages(value: str, user_messages: Iterable[str]) -> bool:
    """
    True if every token of `value` occurs in what the user has typed.

    Token-based so reformatting (added commas, changed capitalization or
    ordering) passes, while invented values fail.
    """
    wanted = _tokens(value)
    if not wanted:
        return False
    typed = set()
    for message in user_messages:
        typed.update(_tokens(message))
    return all(t in typed for t in wanted)


def unverified_fields(buyer_info: Dict[str, str], user_messages: Iterable[str]) -> List[str]:
    """Names of buyer_info fields whose values the user never typed."""
    messages = list(user_messages)
    return [
        field
        for field in ("buyer_name", "buyer_email", "shipping_address")
        if not appears_in_user_messages(buyer_info.get(field, ""), messages)
    ]


def missing_address_parts(address: Dict[str, str]) -> List[str]:
    """Human-readable names of address parts the parser could not find."""
    labels = {
        "street_address": "street address",
        "address_locality": "city",
        "address_region": "state",
        "postal_code": "ZIP code",
    }
    return [label for key, label in labels.items() if not address.get(key)]
