"""Tests for the 2026-08-25 fulfillment request shape.

The live merchant currently returns HTTP 500 for a valid fulfillment PUT, so
end-to-end behavior is covered by the skipped test at the bottom.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.chatbot.services.checkout_service import CheckoutService
from src.chatbot.conversation.state import ConversationState
from src.chatbot.ucp.client import UCPError

ADDRESS = {"street_address": "12 Oak Ave", "address_locality": "Austin",
           "address_region": "TX", "postal_code": "78701", "address_country": "US"}

CHECKOUT = {
    "id": "chk_1", "status": "ready_for_complete", "currency": "USD",
    "line_items": [{"id": "li_1", "item": {"id": "bouquet_sunflowers", "title": "Sunflowers", "price": 2500},
                    "quantity": 1, "totals": []}],
    "totals": [{"type": "total", "amount": 2500}], "links": [], "ucp": {"version": "2026-08-25"},
}


def offered(checkout):
    """Checkout as the merchant would return it after a destination is set."""
    out = dict(checkout)
    out["fulfillment"] = {"methods": [{
        "id": "method_1", "type": "shipping", "line_item_ids": ["li_1"],
        "destinations": [{"id": "dest_1", "type": "shipping", **ADDRESS}],
        "selected_destination_id": "dest_1",
        "groups": [{"id": "g1", "line_item_ids": ["li_1"],
                    "options": [{"id": "std", "title": "Standard"}, {"id": "exp", "title": "Express"}],
                    "selected_option_id": None}]}]}
    return out


def state():
    s = ConversationState(user_id="u", session_id="s")
    s.checkout_id = "chk_1"
    return s


async def test_first_put_sends_spec_valid_method_and_destination():
    client = MagicMock()
    client.get_checkout = AsyncMock(return_value=CHECKOUT)
    client.update_checkout = AsyncMock(side_effect=lambda cid, body, tok=None: offered(CHECKOUT))

    await CheckoutService(client).setup_fulfillment(state(), ADDRESS, "tok")

    first = client.update_checkout.call_args_list[0].args[1]
    method = first["fulfillment"]["methods"][0]
    assert method["id"] and method["type"] == "shipping"
    assert method["line_item_ids"] == ["li_1"]
    dest = method["destinations"][0]
    assert dest["id"] and dest["type"] == "shipping"
    assert dest["street_address"] == "12 Oak Ave"          # flat, not nested
    assert "postal_address" not in dest
    assert method["selected_destination_id"] == dest["id"]
    # line item ids are resent so the full-replacement PUT keeps the cart
    assert first["line_items"][0]["id"] == "li_1"


async def test_put_body_drops_response_only_fields():
    client = MagicMock()
    client.get_checkout = AsyncMock(return_value=CHECKOUT)
    client.update_checkout = AsyncMock(side_effect=lambda cid, body, tok=None: offered(CHECKOUT))

    await CheckoutService(client).setup_fulfillment(state(), ADDRESS)

    for call in client.update_checkout.call_args_list:
        body = call.args[1]
        for response_only in ("totals", "links", "status", "ucp"):
            assert response_only not in body


async def test_second_put_selects_first_offered_option():
    client = MagicMock()
    client.get_checkout = AsyncMock(return_value=CHECKOUT)
    client.update_checkout = AsyncMock(side_effect=lambda cid, body, tok=None: offered(CHECKOUT))

    await CheckoutService(client).setup_fulfillment(state(), ADDRESS)

    second = client.update_checkout.call_args_list[1].args[1]
    group = second["fulfillment"]["methods"][0]["groups"][0]
    assert group["selected_option_id"] == "std"


async def test_merchant_token_is_passed_on_every_call():
    client = MagicMock()
    client.get_checkout = AsyncMock(return_value=CHECKOUT)
    client.update_checkout = AsyncMock(side_effect=lambda cid, body, tok=None: offered(CHECKOUT))

    await CheckoutService(client).setup_fulfillment(state(), ADDRESS, "tok")

    assert client.get_checkout.call_args.args[1] == "tok"
    assert all(c.args[2] == "tok" for c in client.update_checkout.call_args_list)


async def test_no_offered_options_is_an_error_not_a_silent_success():
    no_options = dict(CHECKOUT)
    no_options["fulfillment"] = {"methods": [{"id": "method_1", "type": "shipping",
                                              "line_item_ids": ["li_1"], "groups": []}]}
    client = MagicMock()
    client.get_checkout = AsyncMock(return_value=CHECKOUT)
    client.update_checkout = AsyncMock(return_value=no_options)

    with pytest.raises(ValueError, match="no shipping options"):
        await CheckoutService(client).setup_fulfillment(state(), ADDRESS)
    assert client.update_checkout.call_count == 1


async def test_empty_cart_cannot_be_fulfilled():
    client = MagicMock()
    client.get_checkout = AsyncMock(return_value={**CHECKOUT, "line_items": []})
    with pytest.raises(ValueError):
        await CheckoutService(client).setup_fulfillment(state(), ADDRESS)


# --- UCPError.user_message ---------------------------------------------

def test_developer_facing_validation_errors_are_not_shown_to_shoppers():
    err = UCPError(422, [{"type": "error", "code": "INVALID_REQUEST", "severity": "unrecoverable",
                          "content": "Field required at fulfillment.methods[0].line_item_ids"}])
    text = err.user_message()
    assert "line_item_ids" not in text and "INVALID_REQUEST" in text


def test_buyer_actionable_errors_are_shown_verbatim():
    err = UCPError(402, [{"type": "error", "code": "INSUFFICIENT_FUNDS", "severity": "requires_buyer_input",
                          "content": "Payment Failed: Insufficient Funds (Mock)"}])
    assert err.user_message() == "Payment Failed: Insufficient Funds (Mock)"


def test_non_json_500_gets_a_generic_message():
    assert "500" in UCPError(500, [], body="Internal Server Error").user_message()


@pytest.mark.skip(reason="Merchant bug: a valid fulfillment PUT returns HTTP 500 (see docs/ucp-2026-08-25-notes.md §6)")
async def test_fulfillment_end_to_end_against_live_merchant():
    ...


# --- payment body ------------------------------------------------------

async def test_complete_sends_spec_payment_body_and_uses_merchant_status():
    from src.chatbot.services.payment_service import PaymentService

    client = MagicMock()
    client.complete_checkout = AsyncMock(return_value={"status": "completed", "order": {"id": "o1", "permalink_url": "https://m/o1"}})
    st = state()

    out = await PaymentService(client).complete_checkout(
        st, {"buyer_name": "Jane Smith", "buyer_email": "jane@example.com",
             "shipping_address": "12 Oak Ave, Austin, TX 78701"}, "tok")

    body = client.complete_checkout.call_args.args[1]
    assert "payment_data" not in body
    instrument = body["payment"]["instruments"][0]
    assert instrument["handler_id"] == "mock_payment_handler"
    assert instrument["credential"] == {"type": "token", "token": "success_token"}
    assert "type" not in instrument["billing_address"]       # no schema.org "PostalAddress" marker
    assert body["risk_signals"]["ip_address"]                # merchant still requires this
    assert client.complete_checkout.call_args.args[2] == "tok"
    assert st.status == "completed" and out["order"]["id"] == "o1"


async def test_complete_in_progress_is_not_reported_as_completed():
    from src.chatbot.services.payment_service import PaymentService

    client = MagicMock()
    client.complete_checkout = AsyncMock(return_value={"status": "complete_in_progress"})
    st = state()
    await PaymentService(client).complete_checkout(
        st, {"buyer_name": "J", "buyer_email": "j@e.co", "shipping_address": "1 A St, B, TX 78701"})
    assert st.status == "complete_in_progress"


# --- cart merging --------------------------------------------------------

def line(lid, pid, qty=1):
    return {"id": lid, "item": {"id": pid, "title": pid.title(), "price": 2500}, "quantity": qty,
            "totals": [{"type": "total", "amount": 2500 * qty}]}


def test_adding_a_product_already_in_the_cart_increases_its_quantity():
    merged = CheckoutService.merge_line_item([line("li_1", "roses")], "roses", 1)
    assert merged == [{"id": "li_1", "item": {"id": "roses"}, "quantity": 2}]


def test_adding_a_new_product_appends_a_line_and_keeps_existing_ids():
    merged = CheckoutService.merge_line_item([line("li_1", "roses", 2)], "tulips", 3)
    assert merged == [{"id": "li_1", "item": {"id": "roses"}, "quantity": 2},
                      {"item": {"id": "tulips"}, "quantity": 3}]


def test_merge_sends_only_request_valid_fields():
    merged = CheckoutService.merge_line_item([line("li_1", "roses")], "tulips", 1)
    for entry in merged:
        assert set(entry) <= {"id", "item", "quantity"}
        assert set(entry["item"]) == {"id"}                  # title/price/totals are response-only


def test_merging_into_a_cart_that_already_has_duplicates_increases_only_the_first():
    merged = CheckoutService.merge_line_item([line("a", "roses"), line("b", "roses")], "roses", 1)
    assert [m["quantity"] for m in merged] == [2, 1]


async def test_add_item_sends_one_line_of_two_for_a_repeated_product():
    client = MagicMock()
    client.get_checkout = AsyncMock(return_value={**CHECKOUT, "line_items": [line("li_1", "bouquet_sunflowers")]})
    client.update_checkout = AsyncMock(return_value=CHECKOUT)
    await CheckoutService(client).add_item(state(), "bouquet_sunflowers", 1, None, "tok")

    body = client.update_checkout.call_args.args[1]
    assert body["line_items"] == [{"id": "li_1", "item": {"id": "bouquet_sunflowers"}, "quantity": 2}]
    assert client.update_checkout.call_args.args[2] == "tok"


async def test_add_item_starts_a_new_checkout_when_the_old_one_is_completed():
    client = MagicMock()
    client.get_checkout = AsyncMock(return_value={**CHECKOUT, "status": "completed"})
    client.create_checkout_with_payload = AsyncMock(return_value={"id": "chk_2"})
    st = state()
    await CheckoutService(client).add_item(st, "bouquet_roses", 2, None, "tok")

    client.update_checkout.assert_not_called()
    payload = client.create_checkout_with_payload.call_args.args[0]
    assert payload["line_items"] == [{"item": {"id": "bouquet_roses"}, "quantity": 2}]
    assert st.checkout_id == "chk_2"


async def test_zero_quantity_is_rejected():
    with pytest.raises(ValueError):
        await CheckoutService(MagicMock()).add_item(state(), "bouquet_roses", 0)
