"""Tests for the connect-to-merchant invitation shown after the first product list."""
import pytest

from src.chatbot.conversation.state import ConversationState
from src.chatbot.services.merchant_connect import (
    CONNECT_PROMPT,
    merchant_token_usable,
    should_offer_connect,
)

not_expired = lambda _: False
expired = lambda _: True


def offer(**overrides):
    args = dict(signed_in=True, found_products=True, token_usable=False, already_offered=False)
    args.update(overrides)
    return should_offer_connect(**args)


def test_offered_after_first_product_list_to_a_signed_in_shopper():
    assert offer()


@pytest.mark.parametrize("override", [
    {"signed_in": False},         # anonymous browsing: nothing to link yet
    {"found_products": False},    # nothing was shown
    {"token_usable": True},       # already connected
    {"already_offered": True},    # once per session
])
def test_not_offered_when_any_condition_fails(override):
    assert not offer(**override)


def test_prompt_explains_the_loyalty_benefit_and_the_access_given():
    assert "loyalty points" in CONNECT_PROMPT.lower()
    assert "checkout" in CONNECT_PROMPT.lower() or "orders" in CONNECT_PROMPT.lower()


# --- token usability ----------------------------------------------------

def test_no_token_is_unusable():
    assert not merchant_token_usable(None, not_expired)
    assert not merchant_token_usable({}, not_expired)
    # a half-started flow only has the PKCE verifier parked on the session
    assert not merchant_token_usable({"pending_code_verifier": "v"}, not_expired)


def test_valid_token_is_usable():
    assert merchant_token_usable({"access_token": "t", "expires_at": "2099-01-01T00:00:00Z"}, not_expired)


def test_expired_token_without_refresh_is_unusable_so_the_shopper_is_invited_again():
    assert not merchant_token_usable({"access_token": "t", "expires_at": "2020-01-01T00:00:00Z"}, expired)


def test_expired_token_with_refresh_is_still_usable():
    assert merchant_token_usable(
        {"access_token": "t", "refresh_token": "r", "expires_at": "2020-01-01T00:00:00Z"}, expired)


# --- state persistence --------------------------------------------------

def test_offer_flag_survives_a_dynamodb_round_trip():
    state = ConversationState(user_id="u", session_id="s")
    assert state.connect_offered is False
    state.connect_offered = True
    restored = ConversationState.from_dynamodb_item(state.to_dynamodb_item())
    assert restored.connect_offered is True


def test_sessions_saved_before_this_change_load_with_the_flag_off():
    item = ConversationState(user_id="u", session_id="s").to_dynamodb_item()
    item.pop("connect_offered")
    assert ConversationState.from_dynamodb_item(item).connect_offered is False
