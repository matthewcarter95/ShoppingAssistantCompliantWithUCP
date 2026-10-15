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


def points_question_answered(messages: Iterable) -> bool:
    """
    True once the assistant has asked about loyalty points and the shopper
    has replied since.

    The model is told to ask at every checkout; this makes that rule hold even
    if it forgets. `messages` are conversation Message objects in order.
    """
    asked_at = None
    for i, message in enumerate(messages):
        if message.role == "assistant" and re.search(r"\b(points?|petals?|rewards?)\b", message.content, re.I):
            asked_at = i
    if asked_at is None:
        return False
    return any(m.role == "user" for m in list(messages)[asked_at + 1:])


def dollars_to_cents(value) -> int:
    """Convert a dollar amount (number or string) to whole cents, rounding half up."""
    from decimal import ROUND_HALF_UP, Decimal

    cents = (Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


_AFFIRMATIVE = re.compile(
    r"^\s*(yes|yep|yeah|yup|y|correct|right|that'?s (right|correct)|looks good|"
    r"confirm(ed)?|ok(ay)?|sure|go ahead|please do|do it)\b",
    re.IGNORECASE,
)
_CORRECTION = re.compile(r"\b(no|not|nope|change|instead|wrong|actually|but|different)\b", re.IGNORECASE)


def confirmation_shown_index(messages, profile) -> int:
    """
    Index of the latest assistant message that showed `profile` to the shopper
    (it must contain the email and the street), or -1.
    """
    messages = list(messages)
    street = profile.address.get("street_address", "").lower()
    email = profile.email.lower()
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.role == "assistant" and email in m.content.lower() and street in m.content.lower():
            return i
    return -1


def details_confirmed(messages, profile) -> bool:
    """
    True if the shopper replied to the details confirmation with a plain yes.

    Only the first user message after the confirmation counts, and any
    correction wording ("no", "change", "but"...) cancels it, so "yes but ship
    it to my office" is not a confirmation.
    """
    messages = list(messages)
    shown = confirmation_shown_index(messages, profile)
    if shown < 0:
        return False
    reply = next((m.content for m in messages[shown + 1:] if m.role == "user"), None)
    if reply is None:
        return False
    return bool(_AFFIRMATIVE.match(reply)) and not _CORRECTION.search(reply)
