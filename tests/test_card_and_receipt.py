"""Tests for saved-card selection and the order receipt."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.chatbot.conversation.state import ConversationState
from src.chatbot.services.checkout_payment import (
    ASK, CARD_QUESTION_MARKER, CHOSEN, SavedCard, build_receipt, card_prompt,
    format_money, resolve_card_choice, saved_cards_from,
)
from src.chatbot.services.payment_service import PaymentService

BUYER = {"buyer_name": "Sam Edgar", "buyer_email": "sme@atko.email",
         "shipping_address": "25 Scribner Park, Auburndale, MA 02466"}


def msg(role, content):
    return SimpleNamespace(role=role, content=content)


def card_instrument(cid, brand, last4, default=False, **extra):
    return {"id": cid, "handler_id": "mock_payment_handler", "type": "card",
            "display": {"brand": brand, "last_digits": last4, "expiry_month": 7, "expiry_year": 2099,
                        "description": f"{brand.title()} ending in {last4}, expires 07/2099", "default": default},
            **extra}


POINTS = {"id": "loyalty_abc", "handler_id": "mock_loyalty_points", "type": "loyalty",
          "display": {"balance_points": 2810, "max_redeemable_points": 1750}}


def checkout(*instruments):
    return {"id": "chk_1", "payment": {"instruments": list(instruments)}}


VISA = card_instrument("pm_aaa", "visa", "4242", default=True)
AMEX = card_instrument("pm_bbb", "amex", "4321")


# --- reading the merchant's cards -----------------------------------------

def test_cards_are_read_from_payment_instruments_and_points_are_not_cards():
    cards = saved_cards_from(checkout(POINTS, VISA, AMEX))
    assert [c.id for c in cards] == ["pm_aaa", "pm_bbb"]
    assert cards[0].default and not cards[1].default
    assert cards[1].label() == "Amex ending in 4321, expires 07/2099"


def test_no_cards_when_the_merchant_offers_none():
    assert saved_cards_from(checkout(POINTS)) == []
    assert saved_cards_from({"id": "x"}) == []


def test_instruments_that_carry_a_credential_or_lack_display_are_not_offered_cards():
    with_credential = card_instrument("pm_c", "visa", "1111", credential={"type": "token", "token": "t"})
    no_display = {"id": "pm_d", "handler_id": "mock_payment_handler", "type": "card"}
    assert saved_cards_from(checkout(with_credential, no_display)) == []


# --- choosing a card from what the shopper typed ---------------------------

def asked(cards):
    return msg("assistant", card_prompt(cards))


def choose(reply, cards=None):
    cards = cards or saved_cards_from(checkout(VISA, AMEX))
    return resolve_card_choice([msg("user", "checkout"), asked(cards), msg("user", reply)], cards)


def test_card_question_is_asked_first():
    cards = saved_cards_from(checkout(VISA, AMEX))
    d = resolve_card_choice([msg("user", "checkout")], cards)
    assert d.kind == ASK and CARD_QUESTION_MARKER in d.message
    assert "1. Visa ending in 4242" in d.message and "(default)" in d.message and "2. Amex" in d.message


def test_question_without_a_reply_is_asked_again_not_answered():
    cards = saved_cards_from(checkout(VISA, AMEX))
    assert resolve_card_choice([asked(cards)], cards).kind == ASK


@pytest.mark.parametrize("reply,expected", [
    ("2", "pm_bbb"), ("#1", "pm_aaa"), ("number 2", "pm_bbb"),
    ("amex", "pm_bbb"), ("the Visa please", "pm_aaa"), ("American Express", "pm_bbb"),
    ("4321", "pm_bbb"), ("the one ending in 4242", "pm_aaa"),
    ("yes", "pm_aaa"), ("use the default", "pm_aaa"),
])
def test_replies_that_identify_one_card(reply, expected):
    d = choose(reply)
    assert d.kind == CHOSEN and d.card.id == expected


@pytest.mark.parametrize("reply", ["3", "0", "mastercard", "9999", "hmm", "either", "both"])
def test_unclear_replies_ask_again_and_say_so(reply):
    d = choose(reply)
    assert d.kind == ASK and d.message.startswith("I couldn't tell which card")


def test_yes_is_ambiguous_with_several_cards_and_no_default():
    cards = saved_cards_from(checkout(card_instrument("pm_1", "visa", "1111"), card_instrument("pm_2", "amex", "2222")))
    assert choose("yes", cards).kind == ASK


def test_a_single_card_is_chosen_by_yes():
    cards = saved_cards_from(checkout(VISA))
    d = choose("yes", cards)
    assert d.kind == CHOSEN and d.card.id == "pm_aaa"
    assert "has Visa ending in 4242" in card_prompt(cards)


def test_two_cards_of_one_brand_need_more_than_the_brand():
    cards = saved_cards_from(checkout(card_instrument("pm_1", "visa", "1111"), card_instrument("pm_2", "visa", "2222")))
    assert choose("visa", cards).kind == ASK
    assert choose("visa 2222", cards).card.id == "pm_2"


def test_a_reply_from_before_the_question_does_not_count():
    cards = saved_cards_from(checkout(VISA, AMEX))
    assert resolve_card_choice([msg("user", "amex"), asked(cards)], cards).kind == ASK


# --- completion sends only the card id --------------------------------------

def state():
    s = ConversationState(user_id="u", session_id="s")
    s.checkout_id = "chk_1"
    return s


def completing_client():
    c = MagicMock()
    c.complete_checkout = AsyncMock(return_value={"status": "completed", "order": {"id": "o1"}})
    return c


async def test_saved_card_is_sent_by_id_with_no_credential_or_billing_address():
    c = completing_client()
    card = saved_cards_from(checkout(VISA, AMEX))[1]
    await PaymentService(c).complete_checkout(state(), BUYER, "tok", card=card)
    instruments = c.complete_checkout.call_args.args[1]["payment"]["instruments"]
    assert instruments == [{"id": "pm_bbb", "handler_id": "mock_payment_handler", "type": "card"}]


async def test_without_a_saved_card_the_mock_test_card_is_still_used():
    c = completing_client()
    await PaymentService(c).complete_checkout(state(), BUYER, "tok")
    only = c.complete_checkout.call_args.args[1]["payment"]["instruments"][0]
    assert only["credential"] == {"type": "token", "token": "success_token"}


# --- receipt, using the real figures from order 3ad01c16 ---------------------

COMPLETED = {
    "status": "completed", "currency": "USD",
    "order": {"id": "3ad01c16-cbb0-4817-bee8-53595dc1aaa3", "permalink_url": "https://m/o"},
    "line_items": [{"item": {"id": "bouquet_roses", "title": "Bouquet of Roses", "price": 3500}, "quantity": 1}],
    "totals": [{"type": "subtotal", "amount": 3500}, {"type": "fulfillment", "amount": 0}, {"type": "total", "amount": 3500}],
    "fulfillment": {"methods": [{"groups": [{"selected_option_id": "standard_us",
                                             "options": [{"id": "standard_us", "title": "Standard Shipping"}]}]}]},
    "payment": {"instruments": [
        {"id": "pts_1", "handler_id": "mock_loyalty_points", "type": "loyalty", "amount": 1750},
        {"id": "pm_bbb", "handler_id": "mock_payment_handler", "type": "card", "amount": 1750}]},
}


def receipt(checkout=COMPLETED, labels=None):
    return build_receipt(checkout, buyer_name="Sam Edgar", address_line="25 Scribner Park, Auburndale, MA 02466",
                         card_labels=labels or {"pm_bbb": "Amex ending in 4321"}, cents_per_point=1, points_name="Petals")


def test_receipt_lists_items_totals_and_what_each_instrument_paid():
    text = receipt()
    assert "Order ID: 3ad01c16-cbb0-4817-bee8-53595dc1aaa3" in text
    assert "1 x Bouquet of Roses ($35.00 each)" in text
    assert "Ship to: Sam Edgar, 25 Scribner Park, Auburndale, MA 02466" in text
    assert "Shipping method: Standard Shipping" in text
    assert "Subtotal: $35.00" in text and "Shipping: $0.00" in text and "Total: $35.00" in text
    assert "- 1,750 Petals: $17.50" in text
    assert "- Amex ending in 4321: $17.50" in text


def test_receipt_amounts_are_the_merchants_not_recomputed():
    odd = {**COMPLETED, "totals": [{"type": "subtotal", "amount": 3500}, {"type": "tax", "amount": 123},
                                   {"type": "total", "amount": 3623}]}
    text = receipt(odd)
    assert "Tax: $1.23" in text and "Total: $36.23" in text


def test_receipt_without_loyalty_has_one_payment_line():
    one = {**COMPLETED, "payment": {"instruments": [
        {"id": "pm_bbb", "handler_id": "mock_payment_handler", "type": "card", "amount": 3500}]}}
    text = receipt(one)
    assert "- Amex ending in 4321: $35.00" in text and "Petals" not in text


def test_receipt_for_an_in_progress_order_does_not_claim_confirmation():
    text = receipt({**COMPLETED, "status": "complete_in_progress", "order": None})
    assert "being processed" in text and "Order confirmed" not in text


def test_points_without_a_currency_name_say_loyalty_points():
    text = build_receipt(COMPLETED, buyer_name="Sam", address_line="x", card_labels={}, points_name=None)
    assert "- 1,750 loyalty points: $17.50" in text


def test_unknown_card_instrument_falls_back_to_a_generic_label():
    assert "- Card: $17.50" in receipt(labels={"something_else": "x"})


def test_discount_and_negative_amounts_format_with_a_sign():
    assert format_money(-250) == "-$2.50" and format_money(123456) == "$1,234.56"
    assert format_money(500, "EUR") == "EUR 5.00"


# --- a second order in the same session is asked again ------------------------

def test_checkout_floor_survives_a_round_trip_and_defaults_to_zero():
    s = ConversationState(user_id="u", session_id="s")
    s.checkout_floor = 12
    assert ConversationState.from_dynamodb_item(s.to_dynamodb_item()).checkout_floor == 12
    item = s.to_dynamodb_item(); item.pop("checkout_floor")
    assert ConversationState.from_dynamodb_item(item).checkout_floor == 0


def test_the_points_question_is_asked_again_after_the_floor_moves():
    from src.chatbot.services.buyer_input import points_question_answered
    history = [msg("assistant", "Would you like to use your loyalty points?"), msg("user", "no"),
               msg("assistant", "Order confirmed."), msg("user", "checkout again")]
    assert points_question_answered(history)
    assert not points_question_answered(history[3:])
