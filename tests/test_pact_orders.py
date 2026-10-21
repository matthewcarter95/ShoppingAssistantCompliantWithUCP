"""check_orders: asking the merchant's agent about orders, with step-up, and what we refuse to show."""
import base64
import json
import time

import httpx
import pytest
from jose import jws

from src.chatbot.conversation.state import ConversationState
from src.chatbot.pact.keys import parse_private_jwk
from src.chatbot.services.pact_orders import (
    MAX_REPLY_CHARS,
    ORDERS_SHOWN,
    PactOrders,
    clean_reply,
    safe_auth_url,
)

ISSUER = "https://assistant.example.com"
AUD = "https://shop.example/a2a"
CARD_URL = "https://shop.example/.well-known/agent-card.json"
IFACE = "https://shop.example/a2a/01"
JWKS_URL = "https://shop.example/a2a/01/oauth/jwks.json"
LOGIN = "https://shop.example/pact/login?return_to=x"
GRANT = "a2agrant_1"

CARD = {
    "name": "Dollar Treasure",
    "supportedInterfaces": [{"url": IFACE, "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"}],
    "securitySchemes": {
        "platformJwt": {"httpAuthSecurityScheme": {"scheme": "Bearer", "bearerFormat": "JWT"}},
        "userDelegation": {"oauth2SecurityScheme": {
            "flows": {"deviceCode": {"deviceAuthorizationUrl": f"{IFACE}/oauth/device_authorization", "tokenUrl": f"{IFACE}/oauth/token",
                                     "scopes": {"orders:read": "View your orders"}}},
            "oauth2MetadataUrl": f"{IFACE}/oauth/.well-known/oauth-authorization-server"}},
    },
    "securityRequirements": [{"schemes": {"platformJwt": {"list": []}}},
                             {"schemes": {"platformJwt": {"list": []}, "userDelegation": {"list": []}}}],
}


def b64(n):
    return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()


def make_key():
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1()).private_numbers()
    private = {"kty": "EC", "crv": "P-256", "x": b64(k.public_numbers.x), "y": b64(k.public_numbers.y), "d": b64(k.private_value)}
    public = {x: private[x] for x in ("kty", "crv", "x", "y")} | {"kid": "k1", "alg": "ES256", "use": "sig"}
    return private, {"keys": [public]}


def access_token(scope="orders:read", ttl=3600):
    claims = {"iss": "i", "sub": "auth0|1", "grant_id": GRANT, "scope": scope, "exp": int(time.time()) + ttl}
    return jws.sign(json.dumps(claims).encode(), "secret", algorithm="HS256")


class Merchant:
    """A stand-in for the merchant's Provider. Records what it was asked; answers like the real one."""

    def __init__(self):
        self.private, self.jwks = make_key()
        self.calls = []
        self.step_up = True            # first order question has no token → step-up
        self.device_status = "pending"  # pending | approved | denied | expired
        self.reply_text = "Order 658089bb: 1 x Sunflowers (processing, 30.00 USD)."
        self.receipt_override = None   # replace the receipt claims to test tampering
        self.reject_delegation = False
        self.login_url = LOGIN
        self.token_scope = "orders:read"
        self.slow_down_once = False

    def receipt(self, scopes=("orders:read",)):
        claims = {"grantId": GRANT, "user": "auth0|1", "pa": ISSUER, "brand": IFACE, "scopesUsed": list(scopes),
                  "actions": [{"tool": "list_orders"}], "ts": "2026-10-20T12:00:00Z"}
        signed = jws.sign(json.dumps(claims, separators=(",", ":")).encode(), self.private, algorithm="ES256",
                          headers={"kid": "k1", "typ": "pact-receipt+jws"})
        return {"jws": signed, "claims": self.receipt_override or claims}

    def handler(self, request):
        url = str(request.url)
        self.calls.append((request.method, url.replace(IFACE, "")))
        if url == CARD_URL:
            return httpx.Response(200, json=CARD)
        if url.endswith("/.well-known/oauth-authorization-server"):
            return httpx.Response(200, json={"jwks_uri": JWKS_URL})
        if url == JWKS_URL:
            return httpx.Response(200, json=self.jwks)
        if url.endswith("/oauth/device_authorization"):
            self.requested = dict(httpx.QueryParams(request.content.decode()))
            return httpx.Response(200, json={"device_code": "dc_1", "user_code": "BCDF-GHJK", "expires_in": 600, "interval": 5,
                                             "verification_uri": self.login_url, "verification_uri_complete": self.login_url})
        if url.endswith("/oauth/token"):
            form = dict(httpx.QueryParams(request.content.decode()))
            if form["grant_type"] == "refresh_token":
                return httpx.Response(200, json={"access_token": access_token(), "refresh_token": "rt2", "expires_in": 3600, "scope": "orders:read"})
            if self.slow_down_once:
                self.slow_down_once = False
                return httpx.Response(400, json={"error": "slow_down"})
            if self.device_status == "pending":
                return httpx.Response(400, json={"error": "authorization_pending"})
            if self.device_status == "denied":
                return httpx.Response(400, json={"error": "access_denied"})
            if self.device_status == "expired":
                return httpx.Response(400, json={"error": "expired_token"})
            return httpx.Response(200, json={"access_token": access_token(self.token_scope), "refresh_token": "rt1", "expires_in": 3600, "scope": self.token_scope})
        if url.endswith("/message:send"):
            has_token = "x-a2a-user-delegation" in request.headers
            body = json.loads(request.content)["message"]
            ctx = body.get("contextId", "ctx-1")
            if has_token and self.reject_delegation:
                return httpx.Response(401, headers={"x-amzn-remapped-www-authenticate": 'Bearer realm="a2a", error="invalid_token"'})
            if not has_token and self.step_up:
                return httpx.Response(200, json={"task": {"id": "t", "contextId": ctx, "status": {"state": "TASK_STATE_AUTH_REQUIRED", "message": {"parts": [{"text": "I need permission to view the customer's orders."}]}},
                                                           "metadata": {"pact.missingScopes": ["orders:read"], "pact.verificationUriComplete": self.login_url}}})
            meta = {"pact.receipt": self.receipt()} if has_token else {}
            return httpx.Response(200, json={"message": {"messageId": "r", "contextId": ctx, "role": "ROLE_AGENT", "parts": [{"text": self.reply_text}], "metadata": meta}})
        return httpx.Response(404)


@pytest.fixture
def merchant():
    return Merchant()


@pytest.fixture
def signing(monkeypatch):
    return lambda sub, aud, **kw: f"agent.jwt.{sub}"


def build(merchant, clock=None, **over):
    http = httpx.AsyncClient(transport=httpx.MockTransport(merchant.handler))
    clock = clock or [time.time()]
    kwargs = dict(card_url=CARD_URL, audience=AUD, issuer=ISSUER, http=http, now=lambda: clock[0],
                  sub_fn=lambda s: "u_opaque", sign_fn=lambda sub, aud, **kw: f"agent.jwt.{sub}")
    kwargs.update(over)
    po = PactOrders(**kwargs)
    po.enabled_override = True
    return po, clock


@pytest.fixture(autouse=True)
def pact_on(monkeypatch):
    import src.chatbot.services.pact_orders as m
    monkeypatch.setattr(m, "pact_enabled", lambda: True)


def new_state():
    return ConversationState(user_id="shopper@example.com", session_id="s1")


class TestAsking:
    async def test_without_a_token_the_shopper_is_sent_to_the_merchant_to_approve(self, merchant):
        po, _ = build(merchant)
        state = new_state()
        out = await po.ask(state, "auth0|1", "Where is my latest order?")
        assert out.kind == "step_up" and out.auth_url == LOGIN
        assert "needs your permission" in out.text and "shop.example" in out.text
        assert merchant.requested["scope"] == "orders:read"
        assert state.pact["pending"]["question"] == "Where is my latest order?"
        assert state.pact["context_id"] == "ctx-1"  # the conversation stays open across the approval

    async def test_the_agent_sub_is_opaque_never_the_shoppers_email_or_auth0_id(self, merchant):
        signed = []
        po, _ = build(merchant, sign_fn=lambda sub, aud, **kw: signed.append((sub, aud)) or "agent.jwt")
        await po.ask(new_state(), "auth0|1", "my orders")
        assert signed and all(s == ("u_opaque", AUD) for s in signed)

    async def test_a_stored_token_is_sent_and_the_reply_is_returned_with_its_receipt_checked(self, merchant):
        po, clock = build(merchant)
        state = new_state()
        state.pact = {"token": {"access_token": access_token(), "refresh_token": "rt", "scopes": ["orders:read"], "expires_at": int(clock[0]) + 3000}}
        out = await po.ask(state, "auth0|1", "Where is my latest order?")
        assert out.kind == "reply" and "Sunflowers" in out.text
        assert state.pact["receipts"][0]["actions"] == ["list_orders"]
        assert state.pact["receipts"][0]["grant_id"] == GRANT

    async def test_the_merchants_context_id_is_remembered_from_its_reply(self, merchant):
        po, clock = build(merchant)
        state = new_state()
        state.pact = {"token": {"access_token": access_token(), "refresh_token": None, "scopes": ["orders:read"], "expires_at": int(clock[0]) + 3000}}
        assert "context_id" not in state.pact
        await po.ask(state, "auth0|1", "orders?")
        assert state.pact["context_id"] == "ctx-1"  # taken from the reply, not invented

    async def test_the_context_id_is_reused_so_the_merchant_keeps_one_conversation(self, merchant):
        po, clock = build(merchant)
        state = new_state()
        state.pact = {"context_id": "ctx-9", "token": {"access_token": access_token(), "refresh_token": None, "scopes": ["orders:read"], "expires_at": int(clock[0]) + 3000}}
        await po.ask(state, "auth0|1", "again")
        assert state.pact["context_id"] == "ctx-9"

    async def test_an_expired_token_is_refreshed_not_re_approved(self, merchant):
        po, clock = build(merchant)
        state = new_state()
        state.pact = {"token": {"access_token": access_token(), "refresh_token": "rt-old", "scopes": ["orders:read"], "expires_at": int(clock[0]) - 5}}
        out = await po.ask(state, "auth0|1", "orders?")
        assert out.kind == "reply"
        assert state.pact["token"]["refresh_token"] == "rt2"

    async def test_a_revoked_token_sends_the_shopper_back_through_approval_once(self, merchant):
        merchant.reject_delegation = True
        po, clock = build(merchant)
        state = new_state()
        state.pact = {"token": {"access_token": access_token(), "refresh_token": None, "scopes": ["orders:read"], "expires_at": int(clock[0]) + 3000}}
        out = await po.ask(state, "auth0|1", "orders?")
        assert out.kind == "step_up"
        assert "token" not in state.pact  # the dead token is gone, not retried forever

    async def test_a_merchant_without_delegation_is_reported_plainly(self, merchant):
        po, _ = build(merchant)
        po._brand_cache = None
        original = merchant.handler

        def no_delegation(request):
            if str(request.url) == CARD_URL:
                return httpx.Response(200, json={**CARD, "securityRequirements": [CARD["securityRequirements"][0]]})
            return original(request)

        po._http = httpx.AsyncClient(transport=httpx.MockTransport(no_delegation))
        out = await po.ask(new_state(), "auth0|1", "orders?")
        assert out.kind == "error" and "doesn't let assistants" in out.text

    async def test_a_merchant_outage_is_a_friendly_error_with_no_internals(self, merchant):
        po, _ = build(merchant)
        po._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
        out = await po.ask(new_state(), "auth0|1", "orders?")
        assert out.kind == "error" and "503" not in out.text and "Traceback" not in out.text


class TestWhatWeRefuseToShow:
    async def _with_token(self, merchant):
        po, clock = build(merchant)
        state = new_state()
        state.pact = {"token": {"access_token": access_token(), "refresh_token": None, "scopes": ["orders:read"], "expires_at": int(clock[0]) + 3000}}
        return po, state

    async def test_a_reply_whose_receipt_does_not_verify_is_not_shown(self, merchant):
        po, state = await self._with_token(merchant)
        forger, _ = make_key()
        merchant.private = forger  # signs with a key that is not in the published JWKS
        out = await po.ask(state, "auth0|1", "orders?")
        assert out.kind == "error" and "Sunflowers" not in out.text

    async def test_tampered_receipt_claims_are_caught(self, merchant):
        po, state = await self._with_token(merchant)
        merchant.receipt_override = {"grantId": GRANT, "user": "auth0|1", "pa": ISSUER, "brand": IFACE, "scopesUsed": ["orders:read", "orders:cancel"],
                                     "actions": [], "ts": "2026-10-20T12:00:00Z"}
        assert (await po.ask(state, "auth0|1", "orders?")).kind == "error"

    async def test_a_receipt_for_a_different_agent_is_rejected(self, merchant):
        po, state = await self._with_token(merchant)
        orig = merchant.receipt

        def other_agent(scopes=("orders:read",)):
            r = orig(scopes)
            claims = {**r["claims"], "pa": "https://someone-else.example"}
            r["jws"] = jws.sign(json.dumps(claims, separators=(",", ":")).encode(), merchant.private, algorithm="ES256", headers={"kid": "k1"})
            r["claims"] = claims
            return r

        merchant.receipt = other_agent
        assert (await po.ask(state, "auth0|1", "orders?")).kind == "error"

    async def test_a_receipt_claiming_scopes_the_shopper_never_granted_is_rejected(self, merchant):
        po, state = await self._with_token(merchant)
        merchant.receipt = lambda scopes=("orders:read", "orders:cancel"): Merchant.receipt(merchant, ("orders:read", "orders:cancel"))
        assert (await po.ask(state, "auth0|1", "orders?")).kind == "error"

    async def test_a_delegated_reply_with_no_receipt_is_not_shown(self, merchant):
        po, state = await self._with_token(merchant)
        original = merchant.handler

        def strip(request):
            r = original(request)
            if str(request.url).endswith("/message:send") and r.status_code == 200:
                body = r.json()
                body["message"]["metadata"] = {}
                return httpx.Response(200, json=body)
            return r

        po._http = httpx.AsyncClient(transport=httpx.MockTransport(strip))
        out = await po.ask(state, "auth0|1", "orders?")
        # the specific refusal, not the catch-all "couldn't reach" message
        assert out.kind == "error" and "Sunflowers" not in out.text and "couldn't verify" in out.text

    async def test_a_rotated_merchant_key_is_picked_up_by_refetching_once(self, merchant):
        po, state = await self._with_token(merchant)
        po._brand_cache = None
        await po._brand()
        po._brand_cache.jwks = {"keys": []}  # stale cache
        assert (await po.ask(state, "auth0|1", "orders?")).kind == "reply"

    def test_merchant_text_is_stripped_of_control_characters_and_capped(self):
        assert clean_reply("a\x1b[31mred\x00\x7f") == "a[31mred"
        assert len(clean_reply("x" * 5000)) == MAX_REPLY_CHARS
        assert clean_reply("   ") == "The merchant sent an empty reply."
        assert clean_reply("line1\nline2") == "line1\nline2"

    @pytest.mark.parametrize("url,ok", [
        ("https://shop.example/pact/login?a=1", True),
        ("http://shop.example/login", False),
        ("javascript:alert(1)", False),
        ("data:text/html,<script>", False),
        ("https://user:pw@shop.example/", False),
        ("//shop.example/x", False),
        ("not a url", False),
        (None, False),
    ])
    def test_only_plain_https_sign_in_links_are_opened(self, url, ok):
        assert (safe_auth_url(url) is not None) is ok

    async def test_a_javascript_sign_in_link_from_the_merchant_is_refused_not_opened(self, merchant):
        merchant.login_url = "javascript:alert(1)"
        po, _ = build(merchant)
        out = await po.ask(new_state(), "auth0|1", "orders?")
        assert out.kind == "error" and out.auth_url is None


class TestResume:
    async def _pending(self, merchant):
        po, clock = build(merchant)
        state = new_state()
        await po.ask(state, "auth0|1", "Where is my latest order?")
        return po, clock, state

    async def test_it_keeps_waiting_while_the_shopper_has_not_approved(self, merchant):
        po, clock, state = await self._pending(merchant)
        clock[0] += 6
        out = await po.resume(state, "auth0|1")
        assert out.kind == "pending" and state.pact["pending"]

    async def test_polling_too_soon_does_not_hit_the_merchant(self, merchant):
        po, clock, state = await self._pending(merchant)
        merchant.calls.clear()
        out = await po.resume(state, "auth0|1")
        assert out.kind == "pending"
        assert not any(c[1].endswith("/oauth/token") for c in merchant.calls)

    async def test_slow_down_lengthens_the_interval_by_five_seconds(self, merchant):
        po, clock, state = await self._pending(merchant)
        merchant.slow_down_once = True
        clock[0] += 6
        out = await po.resume(state, "auth0|1")
        assert out.kind == "pending" and out.interval == 10 and state.pact["pending"]["interval"] == 10

    async def test_approval_answers_the_original_question_in_the_same_conversation(self, merchant):
        po, clock, state = await self._pending(merchant)
        merchant.device_status = "approved"
        merchant.step_up = False
        clock[0] += 6
        out = await po.resume(state, "auth0|1")
        assert out.kind == "reply" and "Sunflowers" in out.text
        assert "pending" not in state.pact and state.pact["token"]["scopes"] == ["orders:read"]
        assert state.pact["context_id"] == "ctx-1"
        assert state.pact["receipts"]

    async def test_denial_ends_the_request_politely(self, merchant):
        po, clock, state = await self._pending(merchant)
        merchant.device_status = "denied"
        clock[0] += 6
        out = await po.resume(state, "auth0|1")
        assert out.kind == "denied" and "didn't get access" in out.text and "pending" not in state.pact

    async def test_an_expired_request_is_reported_and_cleared(self, merchant):
        po, clock, state = await self._pending(merchant)
        clock[0] += 601
        out = await po.resume(state, "auth0|1")
        assert out.kind == "expired" and "pending" not in state.pact

    async def test_a_server_side_expiry_is_reported_too(self, merchant):
        po, clock, state = await self._pending(merchant)
        merchant.device_status = "expired"
        clock[0] += 6
        assert (await po.resume(state, "auth0|1")).kind == "expired"

    async def test_nothing_pending_means_nothing_to_do(self, merchant):
        po, _ = build(merchant)
        assert (await po.resume(new_state(), "auth0|1")).kind == "none"

    async def test_a_network_blip_while_polling_keeps_waiting(self, merchant):
        po, clock, state = await self._pending(merchant)
        po._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down"))))
        clock[0] += 6
        out = await po.resume(state, "auth0|1")
        assert out.kind == "pending" and state.pact["pending"]


class TestSessionRoundTrip:
    async def test_pact_state_survives_dynamodb_serialisation_with_no_floats(self, merchant):
        po, _ = build(merchant)
        state = new_state()
        await po.ask(state, "auth0|1", "orders?")
        item = state.to_dynamodb_item()

        def no_floats(x):
            if isinstance(x, float):
                raise AssertionError(f"float in DynamoDB item: {x}")
            if isinstance(x, dict):
                [no_floats(v) for v in x.values()]
            if isinstance(x, list):
                [no_floats(v) for v in x]

        no_floats(item["pact"])
        again = ConversationState.from_dynamodb_item(item)
        assert again.pact == state.pact
        assert ConversationState.from_dynamodb_item({"user_id": "u", "session_id": "s"}).pact is None
