"""Tests for token-sourced checkout details and their confirmation."""
import base64
import json
from types import SimpleNamespace

import pytest

from src.chatbot.services.buyer_claims import BuyerProfile, buyer_profile_from_token, unverified_claims
from src.chatbot.services.buyer_input import details_confirmed
from src.chatbot.services.checkout_details import ASK, CONFIRM, READY, resolve_checkout_details

NS = "https://demo.okta.com"
ADDRESS_CLAIM = {"id": "9c708820-f889-47c2-9ce5-299d7ef6212a", "label": "Home", "street": "25 Scribner Park",
                 "city": "Auburndale", "state": "Massachusetts", "zip": "02466", "country": "US"}


def jwt(claims):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


def token(**overrides):
    claims = {f"{NS}/name": "Matt Carter", f"{NS}/email": "matt@example.com",
              f"{NS}/shippingAddress": ADDRESS_CLAIM}
    claims.update(overrides)
    return jwt({k: v for k, v in claims.items() if v is not None})


def profile():
    return buyer_profile_from_token(token(), NS)


def msg(role, content):
    return SimpleNamespace(role=role, content=content)


def parse(line):                       # stand-in for PaymentService._parse_address
    parts = [p.strip() for p in line.split(",")]
    out = {"street_address": parts[0]}
    if len(parts) > 1: out["address_locality"] = parts[1]
    if len(parts) > 2:
        region, _, zip_ = parts[2].partition(" ")
        out.update(address_region=region, postal_code=zip_)
    return out


# --- claim parsing ------------------------------------------------------

def test_reads_name_email_and_maps_address_to_ucp_fields():
    p = profile()
    assert (p.name, p.email, p.address_label) == ("Matt Carter", "matt@example.com", "Home")
    assert p.address == {"street_address": "25 Scribner Park", "address_locality": "Auburndale",
                         "address_region": "Massachusetts", "postal_code": "02466", "address_country": "US"}


def test_address_line_for_display():
    assert profile().address_line() == "25 Scribner Park, Auburndale, Massachusetts 02466"


def test_namespace_trailing_slash_is_tolerated():
    assert buyer_profile_from_token(token(), NS + "/") is not None


def test_wrong_namespace_finds_nothing_instead_of_guessing():
    assert buyer_profile_from_token(token(), "https://demo.oka.com") is None


@pytest.mark.parametrize("missing", [f"{NS}/name", f"{NS}/email", f"{NS}/shippingAddress"])
def test_any_missing_claim_returns_none(missing):
    assert buyer_profile_from_token(token(**{missing: None}), NS) is None


@pytest.mark.parametrize("bad", [None, "", "abc", "a.b", "a.%%%.c", jwt([1, 2])])
def test_unreadable_tokens_return_none(bad):
    assert unverified_claims(bad) == {} or isinstance(unverified_claims(bad), dict)
    assert buyer_profile_from_token(bad, NS) is None


def test_address_without_street_city_or_zip_is_unusable():
    for broken in ({**ADDRESS_CLAIM, "street": ""}, {**ADDRESS_CLAIM, "city": None}, {**ADDRESS_CLAIM, "zip": None}):
        assert buyer_profile_from_token(token(**{f"{NS}/shippingAddress": broken}), NS) is None


def test_a_list_of_addresses_uses_the_first_and_shows_its_label():
    other = {**ADDRESS_CLAIM, "label": "Work", "street": "1 Main St"}
    p = buyer_profile_from_token(token(**{f"{NS}/shippingAddress": [ADDRESS_CLAIM, other]}), NS)
    assert p.address_label == "Home" and p.address["street_address"] == "25 Scribner Park"


def test_claim_values_are_trimmed():
    p = buyer_profile_from_token(token(**{f"{NS}/name": "  Matt Carter "}), NS)
    assert p.name == "Matt Carter"


# --- confirmation matching ---------------------------------------------

def shown(p):
    from src.chatbot.services.checkout_details import confirmation_prompt
    return msg("assistant", confirmation_prompt(p))


@pytest.mark.parametrize("reply", ["yes", "Yes", "yep", "correct", "that's right", "looks good", "Yes, please", "ok", "go ahead"])
def test_plain_yes_confirms(reply):
    p = profile()
    assert details_confirmed([shown(p), msg("user", reply)], p)


@pytest.mark.parametrize("reply", [
    "no", "no, ship it to my office", "yes but use my work address", "actually change the email",
    "different address please", "hmm", "what address is that?", "",
])
def test_anything_but_a_plain_yes_does_not_confirm(reply):
    p = profile()
    assert not details_confirmed([shown(p), msg("user", reply)], p)


def test_no_confirmation_without_the_details_being_shown():
    assert not details_confirmed([msg("assistant", "Ready to check out?"), msg("user", "yes")], profile())


def test_yes_before_the_details_were_shown_does_not_count():
    p = profile()
    assert not details_confirmed([msg("user", "yes"), shown(p)], p)


def test_only_the_reply_right_after_the_prompt_counts():
    p = profile()
    msgs = [shown(p), msg("user", "no"), msg("assistant", "Okay"), msg("user", "yes")]
    assert not details_confirmed(msgs, p)


# --- decision ----------------------------------------------------------

def decide(messages, arguments=None, tok_profile="default"):
    tp = profile() if tok_profile == "default" else tok_profile
    return resolve_checkout_details(messages, arguments or {}, tp, parse)


def test_saved_details_are_shown_first_not_used():
    d = decide([msg("user", "check out")])
    assert d.kind == CONFIRM
    assert "matt@example.com" in d.message and "25 Scribner Park" in d.message and "Home" in d.message


def test_confirmed_saved_details_are_used_with_the_structured_address():
    p = profile()
    d = decide([msg("user", "check out"), shown(p), msg("user", "yes")])
    assert d.kind == READY and d.source == "token"
    assert d.address["address_region"] == "Massachusetts" and d.address["postal_code"] == "02466"
    assert d.buyer_info["buyer_email"] == "matt@example.com"


def test_model_supplied_details_do_not_override_saved_details():
    p = profile()
    args = {"buyer_name": "John Doe", "buyer_email": "john.doe@example.com", "shipping_address": "123 Flower Street"}
    d = decide([msg("user", "check out"), shown(p), msg("user", "yes")], args)
    assert d.kind == READY and d.buyer_info["buyer_name"] == "Matt Carter"


def test_model_cannot_skip_the_confirmation_by_inventing_details():
    args = {"buyer_name": "John Doe", "buyer_email": "john.doe@example.com", "shipping_address": "123 Flower Street"}
    assert decide([msg("user", "check out")], args).kind == CONFIRM


def test_rejecting_saved_details_requires_typed_ones():
    p = profile()
    d = decide([msg("user", "check out"), shown(p), msg("user", "no, use my office")])
    assert d.kind == ASK and "did not accept" in d.message


def test_typed_details_still_work_and_win_over_saved_ones():
    typed = [msg("user", "I'm Jane Smith, jane@example.com, ship to 12 Oak Ave, Austin, TX 78701")]
    args = {"buyer_name": "Jane Smith", "buyer_email": "jane@example.com", "shipping_address": "12 Oak Ave, Austin, TX 78701"}
    d = decide(typed, args)
    assert d.kind == READY and d.source == "typed" and d.buyer_info["buyer_name"] == "Jane Smith"


def test_without_saved_details_invented_values_are_rejected():
    args = {"buyer_name": "John Doe", "buyer_email": "john.doe@example.com", "shipping_address": "123 Flower Street"}
    d = decide([msg("user", "check out")], args, tok_profile=None)
    assert d.kind == ASK and "Do not guess" in d.message


def test_typed_but_incomplete_address_is_sent_back():
    typed = [msg("user", "Jane Smith jane@example.com 12 Oak Ave")]
    args = {"buyer_name": "Jane Smith", "buyer_email": "jane@example.com", "shipping_address": "12 Oak Ave"}
    d = decide(typed, args, tok_profile=None)
    assert d.kind == ASK and "incomplete" in d.message


def test_summary_text_contains_everything_the_match_needs():
    p = profile()
    text = p.summary()
    assert p.email in text and p.address["street_address"] in text


# --- server-driven checkout sequence -----------------------------------

from src.chatbot.services.checkout_details import (  # noqa: E402
    STAGE_DETAILS, STAGE_POINTS, points_offer, should_force_complete_order, wants_checkout)


@pytest.mark.parametrize("text", ["checkout", "Check out", "let's check out please", "complete_order",
                                  "complete my order", "place order", "proceed to checkout", "buy now"])
def test_checkout_phrases_are_recognized(text):
    assert wants_checkout(text)


@pytest.mark.parametrize("text", ["add roses", "show me tulips", "what's in my cart", "hello", "remove the roses"])
def test_other_requests_are_not_checkout(text):
    assert not wants_checkout(text)


def test_checkout_request_forces_the_tool_only_when_there_is_a_cart():
    assert should_force_complete_order("checkout", True, None)
    assert not should_force_complete_order("checkout", False, None)


def test_reply_to_our_question_forces_the_tool():
    for stage in (STAGE_DETAILS, STAGE_POINTS):
        assert should_force_complete_order("yes", True, stage)
        assert should_force_complete_order("$5", True, stage)
        assert should_force_complete_order("no, ship it to my office", True, stage)


def test_unrelated_message_while_a_question_is_open_is_not_forced():
    assert not should_force_complete_order("actually add some tulips", True, STAGE_DETAILS)
    assert not should_force_complete_order("what's in my cart", True, STAGE_POINTS)
    long_message = "I was thinking about this and " + "really " * 30 + "wondering"
    assert not should_force_complete_order(long_message, True, STAGE_DETAILS)


def test_no_open_question_and_no_checkout_intent_is_not_forced():
    assert not should_force_complete_order("yes", True, None)


def test_points_offer_text():
    text = points_offer(50, "Petals")
    assert "Petals" in text and "50%" in text and "$5" in text
    assert "points" in text.lower()          # matched by points_question_answered
