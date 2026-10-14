"""Tests for the UCP client and header generation."""
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from src.chatbot.ucp.client import UCPClient, UCPError
from src.chatbot.ucp.headers import generate_ucp_headers
from src.chatbot.ucp.profile import VersionUnsupported

PROFILE = json.loads((Path(__file__).parent / "fixtures" / "ucp_profile_2026-08-25.json").read_text())
ENDPOINT = PROFILE["ucp"]["services"]["dev.ucp.shopping"][0]["endpoint"]
AGENT = "https://agent.example/.well-known/ucp"


def make_client(handler):
    """UCPClient wired to a mock transport. DNS checks are skipped."""
    client = UCPClient(base_url=ENDPOINT, agent_profile=AGENT)
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.fixture(autouse=True)
def no_dns():
    with patch("src.chatbot.ucp.client.validate_discovery_url"):
        yield


def profile_response(request, doc=None, cache="public, max-age=3600"):
    return httpx.Response(200, json=doc or PROFILE, headers={"cache-control": cache})


# --- headers -----------------------------------------------------------

def test_get_headers_have_agent_and_request_id_only():
    h = generate_ucp_headers(AGENT)
    assert h["UCP-Agent"] == f'profile="{AGENT}"'
    assert "Request-Id" in h
    assert "Idempotency-Key" not in h
    assert "Content-Type" not in h


def test_mutating_headers_add_idempotency_key_and_content_type():
    h = generate_ucp_headers(AGENT, idempotent=True, has_body=True)
    assert "Idempotency-Key" in h and h["Content-Type"] == "application/json"


def test_idempotency_key_can_be_reused_across_retries():
    a = generate_ucp_headers(AGENT, idempotent=True, idempotency_key="k1")
    b = generate_ucp_headers(AGENT, idempotent=True, idempotency_key="k1")
    assert a["Idempotency-Key"] == b["Idempotency-Key"] == "k1"
    assert a["Request-Id"] != b["Request-Id"]


def test_removed_legacy_headers_are_gone():
    h = generate_ucp_headers(AGENT, idempotent=True, has_body=True)
    lowered = {k.lower() for k in h}
    assert "request-signature" not in lowered
    assert "idempotency-key" in lowered and "request-id" in lowered


# --- discovery ---------------------------------------------------------

async def test_discovery_caches_for_max_age():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return profile_response(request)

    client = make_client(handler)
    await client.get_profile()
    await client.get_profile()
    assert calls == ["/.well-known/ucp"]
    await client.get_profile(force_refresh=True)
    assert len(calls) == 2
    await client.close()


async def test_discovery_rejects_wrong_version():
    doc = json.loads(json.dumps(PROFILE))
    doc["ucp"]["version"] = "2026-01-11"
    client = make_client(lambda r: profile_response(r, doc))
    with pytest.raises(VersionUnsupported):
        await client.get_profile()
    await client.close()


async def test_discovery_does_not_follow_redirects():
    client = make_client(lambda r: httpx.Response(302, headers={"location": "https://evil.example/"}))
    with pytest.raises(Exception):
        await client.get_profile()
    await client.close()


async def test_stale_profile_served_when_refresh_fails():
    state = {"fail": False}

    def handler(request):
        return httpx.Response(500) if state["fail"] else profile_response(request)

    client = make_client(handler)
    first = await client.get_profile()
    state["fail"] = True
    assert (await client.get_profile(force_refresh=True)) is first
    await client.close()


async def test_requests_use_endpoint_from_profile_not_config():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/.well-known/ucp":
            return profile_response(request)
        return httpx.Response(200, json={"ucp": {"version": "2026-08-25"}, "products": []})

    client = make_client(handler)
    await client.search_catalog("roses")
    assert seen[-1] == f"{ENDPOINT}/catalog/search"
    await client.close()


# --- requests ----------------------------------------------------------

async def test_search_sends_post_with_spec_headers():
    captured = {}

    def handler(request):
        if request.url.path == "/.well-known/ucp":
            return profile_response(request)
        captured["req"] = request
        return httpx.Response(200, json={"products": [{"id": "p1"}]})

    client = make_client(handler)
    products = await client.search_catalog("roses", merchant_token="tok")
    req = captured["req"]
    assert products == [{"id": "p1"}]
    assert req.method == "POST" and json.loads(req.content) == {"query": "roses"}
    assert req.headers["ucp-agent"] == f'profile="{AGENT}"'
    assert req.headers["authorization"] == "Bearer tok"
    assert "request-id" in req.headers
    await client.close()


async def test_empty_search_query_is_rejected_locally():
    client = make_client(lambda r: profile_response(r))
    with pytest.raises(ValueError):
        await client.search_catalog("  ")
    await client.close()


async def test_get_checkout_has_no_idempotency_key_or_body():
    captured = {}

    def handler(request):
        if request.url.path == "/.well-known/ucp":
            return profile_response(request)
        captured["req"] = request
        return httpx.Response(200, json={"id": "c1"})

    client = make_client(handler)
    await client.get_checkout("c1")
    req = captured["req"]
    assert req.method == "GET" and req.url.path == "/checkout-sessions/c1"
    assert "idempotency-key" not in req.headers and not req.content
    await client.close()


async def test_update_checkout_is_put_with_idempotency_key():
    captured = {}

    def handler(request):
        if request.url.path == "/.well-known/ucp":
            return profile_response(request)
        captured["req"] = request
        return httpx.Response(200, json={"id": "c1"})

    client = make_client(handler)
    await client.update_checkout("c1", {"line_items": []})
    assert captured["req"].method == "PUT"
    assert "idempotency-key" in captured["req"].headers
    await client.close()


# --- errors ------------------------------------------------------------

async def test_error_surfaces_merchant_messages():
    body = {"messages": [{"type": "error", "code": "INSUFFICIENT_FUNDS",
                          "content": "Payment Failed", "severity": "requires_buyer_input"}]}

    def handler(request):
        if request.url.path == "/.well-known/ucp":
            return profile_response(request)
        return httpx.Response(402, json=body)

    client = make_client(handler)
    with pytest.raises(UCPError) as exc:
        await client.complete_checkout("c1", {})
    assert exc.value.status_code == 402
    assert exc.value.codes == {"INSUFFICIENT_FUNDS"}
    assert "Payment Failed" in str(exc.value)
    await client.close()


async def test_non_json_500_becomes_ucp_error():
    def handler(request):
        if request.url.path == "/.well-known/ucp":
            return profile_response(request)
        return httpx.Response(500, text="Internal Server Error")

    client = make_client(handler)
    with pytest.raises(UCPError) as exc:
        await client.update_checkout("c1", {})
    assert exc.value.status_code == 500 and exc.value.messages == []
    await client.close()


async def test_http_200_with_ucp_status_error_is_an_error():
    body = {"ucp": {"version": "2026-08-25", "status": "error"},
            "messages": [{"type": "error", "code": "capabilities_incompatible", "content": "x",
                          "severity": "unrecoverable"}],
            "continue_url": "https://merchant.example/"}

    def handler(request):
        if request.url.path == "/.well-known/ucp":
            return profile_response(request)
        return httpx.Response(200, json=body)

    client = make_client(handler)
    with pytest.raises(UCPError) as exc:
        await client.create_checkout_with_payload({"line_items": []})
    assert exc.value.codes == {"capabilities_incompatible"}
    assert exc.value.continue_url == "https://merchant.example/"
    await client.close()


async def test_top_level_version_unsupported_error():
    def handler(request):
        if request.url.path == "/.well-known/ucp":
            return profile_response(request)
        return httpx.Response(422, json={"code": "version_unsupported", "content": "nope",
                                         "continue_url": "https://m.example/cart"})

    client = make_client(handler)
    with pytest.raises(UCPError) as exc:
        await client.get_checkout("c1")
    assert exc.value.codes == {"version_unsupported"}
    await client.close()
