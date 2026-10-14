"""Tests for the check that order details came from the user."""
from src.chatbot.services.buyer_input import (
    appears_in_user_messages,
    missing_address_parts,
    unverified_fields,
)

TYPED = ["add sunflowers", "I'm Jane Smith, jane@example.com", "ship to 12 Oak Ave, Austin, TX 78701"]


def test_invented_placeholder_details_are_flagged():
    info = {"buyer_name": "John Doe", "buyer_email": "john.doe@example.com",
            "shipping_address": "123 Flower Street"}
    assert unverified_fields(info, TYPED) == ["buyer_name", "buyer_email", "shipping_address"]


def test_details_the_user_typed_pass_even_when_reformatted():
    info = {"buyer_name": "Jane Smith", "buyer_email": "jane@example.com",
            "shipping_address": "12 Oak Ave, Austin, TX 78701"}
    assert unverified_fields(info, TYPED) == []
    assert appears_in_user_messages("JANE  smith", TYPED)


def test_one_invented_field_among_real_ones():
    info = {"buyer_name": "Jane Smith", "buyer_email": "other@example.com",
            "shipping_address": "12 Oak Ave, Austin, TX 78701"}
    assert unverified_fields(info, TYPED) == ["buyer_email"]


def test_empty_value_is_never_verified():
    assert not appears_in_user_messages("", TYPED)
    assert not appears_in_user_messages("   ", TYPED)


def test_missing_address_parts():
    assert missing_address_parts({"street_address": "123 Flower Street"}) == [
        "city", "state", "ZIP code"]
    assert missing_address_parts({
        "street_address": "12 Oak Ave", "address_locality": "Austin",
        "address_region": "TX", "postal_code": "78701"}) == []
