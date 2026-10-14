"""Tests for merchant profile parsing and capability negotiation."""
import json
from pathlib import Path

import pytest

from src.chatbot.ucp.profile import (
    ProfileError,
    VersionUnsupported,
    check_version,
    is_special_use_address,
    negotiate_capabilities,
    parse_cache_seconds,
    parse_profile,
    validate_discovery_url,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ucp_profile_2026-08-25.json"


@pytest.fixture
def doc():
    return json.loads(FIXTURE.read_text())


def test_parse_real_profile(doc):
    profile = parse_profile(doc)
    assert profile.version == "2026-08-25"
    assert profile.rest_endpoint().startswith("https://")
    assert not profile.rest_endpoint().endswith("/")
    assert profile.keys and profile.keys[0]["alg"] == "ES256"
    assert profile.handler_by_id("mock_payment_handler") is not None
    assert profile.handler_by_id("nope") is None


def test_parse_rejects_missing_required_objects(doc):
    del doc["ucp"]["payment_handlers"]
    with pytest.raises(ProfileError):
        parse_profile(doc)
    with pytest.raises(ProfileError):
        parse_profile({"not": "ucp"})


def test_parse_rejects_non_dated_version(doc):
    doc["ucp"]["version"] = "draft"
    with pytest.raises(ProfileError):
        parse_profile(doc)


def test_check_version(doc):
    check_version(parse_profile(doc))
    doc["ucp"]["version"] = "2026-01-11"
    with pytest.raises(VersionUnsupported):
        check_version(parse_profile(doc))


def test_negotiation_keeps_everything_the_agent_supports(doc):
    caps = negotiate_capabilities(parse_profile(doc))
    assert "dev.ucp.shopping.checkout" in caps
    assert "dev.ucp.shopping.catalog.search" in caps
    assert "dev.ucp.shopping.fulfillment" in caps


def test_negotiation_prunes_orphaned_single_parent_extension(doc):
    del doc["ucp"]["capabilities"]["dev.ucp.shopping.checkout"]
    caps = negotiate_capabilities(parse_profile(doc))
    assert "dev.ucp.shopping.checkout" not in caps
    # fulfillment extends only checkout -> pruned; discount also extends cart -> kept
    assert "dev.ucp.shopping.fulfillment" not in caps
    assert "dev.ucp.shopping.buyer_consent" not in caps
    assert "dev.ucp.shopping.discount" in caps


def test_negotiation_prunes_multi_parent_only_when_all_parents_gone(doc):
    del doc["ucp"]["capabilities"]["dev.ucp.shopping.checkout"]
    del doc["ucp"]["capabilities"]["dev.ucp.shopping.cart"]
    caps = negotiate_capabilities(parse_profile(doc))
    assert "dev.ucp.shopping.discount" not in caps


def test_negotiation_ignores_capabilities_the_agent_does_not_support(doc):
    caps = negotiate_capabilities(parse_profile(doc), agent_capabilities={"dev.ucp.shopping.checkout"})
    assert caps == {"dev.ucp.shopping.checkout"}


@pytest.mark.parametrize("header,expected", [
    ("public, max-age=3600", 3600),
    ("public, max-age=5", 60),            # clamped up to the 60s floor
    ("max-age=999999999", 86400),         # clamped down
    ("no-store", 300),                    # default
    (None, 300),
])
def test_cache_seconds(header, expected):
    assert parse_cache_seconds(header) == expected


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.1.2.3", "192.168.0.1", "169.254.169.254", "::1", "fe80::1", "not-an-ip"])
def test_special_use_addresses_rejected(ip):
    assert is_special_use_address(ip)


def test_public_address_allowed():
    assert not is_special_use_address("8.8.8.8")


def test_discovery_url_must_be_https():
    with pytest.raises(ProfileError):
        validate_discovery_url("http://example.com/.well-known/ucp")


def test_discovery_url_allow_insecure_for_local_dev():
    validate_discovery_url("http://localhost:8000/.well-known/ucp", allow_insecure=True)
