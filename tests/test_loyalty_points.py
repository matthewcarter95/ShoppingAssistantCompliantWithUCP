"""Tests for loyalty-points split payments and merchant re-authorization."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.chatbot.conversation.state import ConversationState
from src.chatbot.services.buyer_input import dollars_to_cents, points_question_answered
from src.chatbot.services.payment_service import PaymentService, PointsRequest, check_points_amount
from src.chatbot.ucp.client import UCPError
from src.chatbot.ucp.profile import parse_profile

FIXTURE = Path(__file__).parent / "fixtures" / "ucp_profile_2026-08-25.json"


def loyalty_doc():
    """The saved profile predates the merchant's loyalty work; add what it advertises.

    Values copied from the live /.well-known/ucp on 2026-10-14.
    """
    doc = json.loads(FIXTURE.read_text())
    ucp = doc["ucp"]
    ucp["capabilities"]["dev.ucp.common.payment.split_payments"] = [{
        "version": "2026-08-25", "extends": "dev.ucp.shopping.checkout",
        "config": {"allowed_combinations": [
            [{"types": ["card", "tokenized_card"], "min": 1, "max": 1}, {"types": ["loyalty"], "max": 1}],
            [{"types": ["loyalty"], "min": 1, "max": 1}]]}}]
    ucp["payment_handlers"]["mock.loyalty_points"] = [{
        "id": "mock_loyalty_points", "name": "mock.loyalty_points", "version": "2026-08-25",
        "config": {"currency": {"name": "Petals", "code": "PTL"},
                   "cents_per_point": 1, "max_redeem_percent": 50}}]
    return doc


PROFILE = parse_profile(loyalty_doc())
CONFIG = {"cents_per_point": 1, "max_redeem_percent": 50}
BUYER = {"buyer_name": "Jane Smith", "buyer_email": "jane@example.com",
         "shipping_address": "12 Oak Ave, Austin, TX 78701"}


def msg(role, content):
    return SimpleNamespace(role=role, content=content)


def state():
    s = ConversationState(user_id="u", session_id="s")
    s.checkout_id = "chk_1"
    return s


def client(profile=PROFILE, total=3000, has_split=True):
    c = MagicMock()
    c.get_profile = AsyncMock(return_value=profile)
    c.has_capability = AsyncMock(return_value=has_split)
    c.get_checkout = AsyncMock(return_value={"totals": [{"type": "total", "amount": total}]})
    c.complete_checkout = AsyncMock(return_value={"status": "completed", "order": {"id": "o1"}})
    return c


def instruments(c):
    return c.complete_checkout.call_args.args[1]["payment"]["instruments"]


# --- cap checks (mirror the merchant's published rules) ----------------

def test_amount_within_cap_is_accepted():
    check_points_amount(1500, 3000, CONFIG)          # exactly 50%


@pytest.mark.parametrize("amount,total,fragment", [
    (0, 3000, r"more than \$0"),
    (-5, 3000, r"more than \$0"),
    (1501, 3000, "at most 50%"),
    (4000, 3000, "more than the order total"),
])
def test_amount_out_of_bounds_is_rejected_with_shopper_text(amount, total, fragment):
    with pytest.raises(ValueError, match=fragment):
        check_points_amount(amount, total, CONFIG)


def test_multiple_of_cents_per_point_is_enforced():
    with pytest.raises(ValueError, match="multiples of 5"):
        check_points_amount(1502, 3000, {"cents_per_point": 5, "max_redeem_percent": 50})


# --- instrument shape ---------------------------------------------------

async def test_no_points_sends_a_single_card_like_before():
    c = client()
    await PaymentService(c).complete_checkout(state(), BUYER, "tok")
    assert [i["handler_id"] for i in instruments(c)] == ["mock_payment_handler"]


async def test_explicit_amount_sends_points_then_card():
    c = client()
    await PaymentService(c).complete_checkout(state(), BUYER, "tok", points=PointsRequest(500))
    pts, card = instruments(c)
    assert pts["handler_id"] == "mock_loyalty_points" and pts["type"] == "loyalty"
    assert pts["amount"] == 500                           # cents
    assert pts["credential"]["type"] == "loyalty"
    assert card["handler_id"] == "mock_payment_handler"
    assert "amount" not in card                           # the merchant charges the remainder
    assert pts["id"] != card["id"]


async def test_open_amount_omits_amount_so_the_merchant_applies_balance_and_cap():
    c = client()
    await PaymentService(c).complete_checkout(state(), BUYER, "tok", points=PointsRequest())
    assert "amount" not in instruments(c)[0]
    c.get_checkout.assert_not_called()                   # nothing to pre-check


async def test_over_cap_amount_never_reaches_the_merchant():
    c = client(total=3000)
    with pytest.raises(ValueError, match="at most 50%"):
        await PaymentService(c).complete_checkout(state(), BUYER, "tok", points=PointsRequest(2000))
    c.complete_checkout.assert_not_called()


async def test_merchant_without_points_support_is_a_clear_error():
    c = client(has_split=False)
    with pytest.raises(ValueError, match="does not accept loyalty points"):
        await PaymentService(c).complete_checkout(state(), BUYER, "tok", points=PointsRequest(500))
    c.complete_checkout.assert_not_called()


async def test_merchant_without_the_points_handler_is_a_clear_error():
    doc = loyalty_doc()
    doc["ucp"]["payment_handlers"].pop("mock.loyalty_points")
    c = client(profile=parse_profile(doc))
    with pytest.raises(ValueError, match="does not accept loyalty points"):
        await PaymentService(c).complete_checkout(state(), BUYER, "tok", points=PointsRequest(500))


# --- the "ask at every checkout" gate ----------------------------------

def test_question_not_asked_yet():
    assert not points_question_answered([msg("user", "checkout"), msg("assistant", "What's your name?")])


def test_asked_but_not_answered():
    assert not points_question_answered([msg("user", "checkout"),
                                         msg("assistant", "Want to use your points?")])


def test_asked_and_answered():
    assert points_question_answered([msg("assistant", "Want to use your loyalty points?"),
                                     msg("user", "yes, $5 worth")])


def test_only_the_latest_question_counts():
    assert not points_question_answered([msg("assistant", "Use points?"), msg("user", "no"),
                                         msg("assistant", "Your points balance changed. Use points?")])


@pytest.mark.parametrize("value,cents", [(5, 500), ("5.00", 500), (12.5, 1250), ("0.005", 1), (0.1 + 0.2, 30)])
def test_dollars_to_cents_avoids_float_error(value, cents):
    assert dollars_to_cents(value) == cents


# --- re-authorization ---------------------------------------------------

def err(status, code):
    return UCPError(status, [{"type": "error", "code": code, "content": "x", "severity": "requires_buyer_review"}])


@pytest.mark.parametrize("status,code,expected", [
    (401, "identity_required", True),
    (403, "insufficient_scope", True),
    (401, "INVALID_REQUEST", False),
    (402, "INSUFFICIENT_FUNDS", False),
    (422, "identity_required", False),
])
def test_needs_reauthorization(status, code, expected):
    assert err(status, code).needs_reauthorization is expected


def test_buyer_review_message_is_shown_to_the_shopper():
    assert err(403, "insufficient_scope").user_message() == "x"


# --- configuration -----------------------------------------------------

def test_requested_scopes_include_manage_and_complete_and_not_the_legacy_scope():
    from src.chatbot.config import settings
    scopes = settings.merchant_auth0_scope.split()
    assert "mock.ucp.shopping.checkout:manage" in scopes
    assert "mock.ucp.shopping.checkout:complete" in scopes
    assert "ucp:scopes:checkout_session" not in scopes
    assert "mock.ucp.shopping.order:read" not in scopes     # the assistant never reads orders


def test_agent_negotiates_loyalty_and_split_payments():
    from src.chatbot.ucp.profile import negotiate_capabilities
    caps = negotiate_capabilities(PROFILE)
    assert "dev.ucp.common.payment.split_payments" in caps
