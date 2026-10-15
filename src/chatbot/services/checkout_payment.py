"""Saved-card selection and the order receipt.

Both are driven by the server from the merchant's own responses:

* The merchant lists the buyer's saved cards in `payment.instruments[]` of a
  checkout, display-only (no credential). The shopper picks one and only its
  `id` is sent back at completion.
* After completion, the receipt is written from the completed checkout
  (line items, typed totals, per-instrument amounts), so the shopper sees real
  numbers instead of a model-written summary.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .buyer_input import is_affirmative

CARD_QUESTION_MARKER = "Which card would you like to use"
LOYALTY_HANDLER_ID = "mock_loyalty_points"

ASK = "ask"
CHOSEN = "chosen"

_TOTAL_LABELS = {
    "subtotal": "Subtotal",
    "items_discount": "Item discounts",
    "discount": "Discount",
    "fulfillment": "Shipping",
    "tax": "Tax",
    "fee": "Fees",
    "total": "Total",
}


@dataclass(frozen=True)
class SavedCard:
    """A card the merchant is holding for this buyer (display data only)."""

    id: str
    handler_id: str
    brand: str
    last_digits: str
    description: str
    default: bool = False

    def label(self) -> str:
        return self.description or f"{self.brand.title()} ending in {self.last_digits}"


def saved_cards_from(checkout: Dict[str, Any]) -> List[SavedCard]:
    """
    Cards the merchant offered on a checkout response.

    Taken from `payment.instruments[]`: entries of type "card" that carry
    display data and no credential. The loyalty-points instrument is not a card.
    """
    cards: List[SavedCard] = []
    for instrument in (checkout.get("payment") or {}).get("instruments") or []:
        if instrument.get("type") != "card" or instrument.get("handler_id") == LOYALTY_HANDLER_ID:
            continue
        display = instrument.get("display") or {}
        if instrument.get("credential") or not instrument.get("id") or not display.get("last_digits"):
            continue
        cards.append(
            SavedCard(
                id=instrument["id"],
                handler_id=instrument.get("handler_id", ""),
                brand=str(display.get("brand") or "card"),
                last_digits=str(display["last_digits"]),
                description=str(display.get("description") or ""),
                default=bool(display.get("default")),
            )
        )
    return cards


def card_prompt(cards: List[SavedCard], retry: bool = False) -> str:
    """The card question shown to the shopper (always contains CARD_QUESTION_MARKER)."""
    lead = "I couldn't tell which card you meant. " if retry else ""
    if len(cards) == 1:
        return (
            f"{lead}{CARD_QUESTION_MARKER}? The merchant has {cards[0].label()} on file. "
            'Reply "yes" to pay with it.'
        )
    lines = [
        f"{i}. {c.label()}{' (default)' if c.default else ''}" for i, c in enumerate(cards, 1)
    ]
    default_hint = ' Reply "yes" for the default card, or' if any(c.default for c in cards) else " Reply with"
    return (
        f"{lead}{CARD_QUESTION_MARKER}? These are saved with the merchant:\n\n"
        + "\n".join(lines)
        + f"\n\n{default_hint} a number, a brand, or the last four digits."
    )


@dataclass
class CardDecision:
    kind: str
    card: Optional[SavedCard] = None
    message: Optional[str] = None


def _match_reply(reply: str, cards: List[SavedCard]) -> Optional[SavedCard]:
    """Match a shopper's reply to exactly one card, or None if unclear."""
    text = reply.strip().lower()

    number = re.fullmatch(r"\W*(?:#|no\.?|number|option|card)?\s*(\d{1,2})\W*", text)
    if number:
        index = int(number.group(1))
        return cards[index - 1] if 1 <= index <= len(cards) else None

    by_digits = [c for c in cards if re.search(rf"(?<!\d){re.escape(c.last_digits)}(?!\d)", text)]
    if len(by_digits) == 1:
        return by_digits[0]

    def brand_in_text(card: SavedCard) -> bool:
        names = {card.brand.lower(), card.brand.lower().replace("_", " ")}
        if card.brand.lower() == "amex":
            names.add("american express")
        return any(n and n in text for n in names)

    by_brand = [c for c in cards if brand_in_text(c)]
    if len(by_brand) == 1:
        return by_brand[0]
    if by_brand:
        return None  # several cards of that brand

    if is_affirmative(reply) or "default" in text:
        if len(cards) == 1:
            return cards[0]
        defaults = [c for c in cards if c.default]
        return defaults[0] if len(defaults) == 1 else None
    return None


def resolve_card_choice(messages: List[Any], cards: List[SavedCard]) -> CardDecision:
    """
    Work out which saved card the shopper chose from what they typed.

    `messages` must already be scoped to the current checkout. The choice comes
    from the shopper's own reply to our question, never from the model.
    """
    messages = list(messages)
    asked_at = next(
        (
            i
            for i in range(len(messages) - 1, -1, -1)
            if messages[i].role == "assistant" and CARD_QUESTION_MARKER in messages[i].content
        ),
        -1,
    )
    if asked_at < 0:
        return CardDecision(ASK, message=card_prompt(cards))
    reply = next((m.content for m in messages[asked_at + 1:] if m.role == "user"), None)
    if reply is None:
        return CardDecision(ASK, message=card_prompt(cards))
    card = _match_reply(reply, cards)
    if card is None:
        return CardDecision(ASK, message=card_prompt(cards, retry=True))
    return CardDecision(CHOSEN, card=card)


# --- receipt -------------------------------------------------------------

def format_money(amount_minor: int, currency: str = "USD") -> str:
    """Minor units to text. Assumes a 2-decimal currency, as the rest of the agent does."""
    sign = "-" if amount_minor < 0 else ""
    value = f"{abs(amount_minor) / 100:,.2f}"
    return f"{sign}${value}" if currency == "USD" else f"{sign}{currency} {value}"


def _selected_shipping_title(checkout: Dict[str, Any]) -> Optional[str]:
    for method in (checkout.get("fulfillment") or {}).get("methods") or []:
        for group in method.get("groups") or []:
            chosen = group.get("selected_option_id")
            for option in group.get("options") or []:
                if option.get("id") == chosen:
                    return option.get("title")
    return None


def build_receipt(
    checkout: Dict[str, Any],
    *,
    buyer_name: str,
    address_line: str,
    card_labels: Dict[str, str],
    cents_per_point: int = 1,
    points_name: Optional[str] = None,
) -> str:
    """
    Write the order confirmation from a completed checkout response.

    Every figure is the merchant's: totals are not recomputed, and the amount
    for each payment instrument is the amount it actually charged.
    """
    currency = checkout.get("currency", "USD")
    order = checkout.get("order") or {}
    lines: List[str] = []

    status = checkout.get("status")
    if status == "complete_in_progress":
        lines.append("Your order is being processed. I'll check it again shortly.")
    else:
        lines.append(f"Order confirmed. Order ID: {order.get('id', 'unknown')}")

    lines.append("")
    for item in checkout.get("line_items") or []:
        info = item.get("item") or {}
        each = format_money(info.get("price", 0), currency)
        lines.append(f"{item.get('quantity', 1)} x {info.get('title') or info.get('id')} ({each} each)")

    lines.append("")
    lines.append(f"Ship to: {buyer_name}, {address_line}")
    shipping = _selected_shipping_title(checkout)
    if shipping:
        lines.append(f"Shipping method: {shipping}")

    lines.append("")
    for total in checkout.get("totals") or []:
        label = total.get("display_text") or _TOTAL_LABELS.get(total.get("type"), str(total.get("type")).title())
        lines.append(f"{label}: {format_money(total.get('amount', 0), currency)}")

    paid = [i for i in (checkout.get("payment") or {}).get("instruments") or [] if i.get("amount") is not None]
    if paid:
        lines.append("")
        lines.append("Paid with:")
        for instrument in paid:
            amount = int(instrument["amount"])
            if instrument.get("handler_id") == LOYALTY_HANDLER_ID:
                points = amount // max(cents_per_point, 1)
                what = f"{points:,} {points_name}" if points_name else f"{points:,} loyalty points"
                lines.append(f"- {what}: {format_money(amount, currency)}")
            else:
                label = card_labels.get(instrument.get("id", "")) or "Card"
                lines.append(f"- {label}: {format_money(amount, currency)}")

    return "\n".join(lines)
