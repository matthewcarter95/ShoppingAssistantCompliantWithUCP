"""PACT Delegated (personal-agent side): step-up, device-code OAuth, delegation header, receipts."""
import base64
import json
import time

import httpx
import pytest
from jose import jws

from src.chatbot.pact.client import AuthRequired, PactClient, PactError, PactHttpError, PactReply
from src.chatbot.pact.delegation import (
    DelegationScheme,
    DelegationToken,
    DeviceAuthorization,
    DeviceCodeClient,
    OAuthError,
    ReceiptError,
    delegation_scheme,
    verify_receipt,
)

CARD = {
    "securitySchemes": {
        "platformJwt": {"httpAuthSecurityScheme": {"scheme": "Bearer", "bearerFormat": "JWT"}},
        "userDelegation": {"oauth2SecurityScheme": {
            "flows": {"deviceCode": {"deviceAuthorizationUrl": "https://p.example/oauth/device_authorization",
                                     "tokenUrl": "https://p.example/oauth/token",
                                     "scopes": {"orders:read": "View your orders and their status"}}},
            "oauth2MetadataUrl": "https://p.example/oauth/.well-known/oauth-authorization-server"}},
    },
    "securityRequirements": [
        {"schemes": {"platformJwt": {"list": []}}},
        {"schemes": {"platformJwt": {"list": []}, "userDelegation": {"list": []}}},
    ],
}
ISSUER = "https://assistant.example.com"


def scheme():
    s = delegation_scheme(CARD)
    assert s is not None
    return s


class TestScheme:
    def test_finds_the_requirement_that_pairs_agent_jwt_with_device_code(self):
        s = scheme()
        assert s.token_url == "https://p.example/oauth/token"
        assert s.scopes == {"orders:read": "View your orders and their status"}

    def test_identity_only_cards_have_no_delegation(self):
        card = {**CARD, "securityRequirements": [CARD["securityRequirements"][0]]}
        assert delegation_scheme(card) is None
        assert delegation_scheme({}) is None

    def test_a_scheme_without_metadata_is_not_usable(self):
        card = json.loads(json.dumps(CARD))
        del card["securitySchemes"]["userDelegation"]["oauth2SecurityScheme"]["oauth2MetadataUrl"]
        assert delegation_scheme(card) is None


def oauth_client(handler, now=lambda: 1000.0):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return DeviceCodeClient(scheme(), ISSUER, lambda: "agent.jwt", http=http, now=now)


class TestDeviceCode:
    async def test_start_authenticates_with_the_agent_jwt_and_sends_client_id(self):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers["authorization"]
            seen["form"] = dict(httpx.QueryParams(request.content.decode()))
            return httpx.Response(200, json={"device_code": "dc_1", "user_code": "BCDF-GHJK", "expires_in": 600, "interval": 5,
                                             "verification_uri": "https://b/login", "verification_uri_complete": "https://b/login?c=1"})

        auth = await oauth_client(handler).start(["orders:read"])
        assert seen["auth"] == "Bearer agent.jwt"
        assert seen["form"] == {"scope": "orders:read", "client_id": ISSUER}
        assert (auth.device_code, auth.interval, auth.expires_at) == ("dc_1", 5, 1600.0)

    async def test_refuses_scopes_that_are_not_on_the_card_without_calling_out(self):
        c = oauth_client(lambda r: pytest.fail("must not be called"))
        for bad in ([], ["orders:cancel"], ["orders:read", "refunds:issue"]):
            with pytest.raises(ValueError):
                await c.start(bad)

    async def test_poll_maps_pending_slow_down_and_the_terminal_errors(self):
        def reply(error):
            return lambda r: httpx.Response(400, json={"error": error})

        assert await oauth_client(reply("authorization_pending")).poll("dc") == "pending"
        assert await oauth_client(reply("slow_down")).poll("dc") == "slow_down"
        for terminal in ("access_denied", "expired_token", "invalid_grant"):
            with pytest.raises(OAuthError) as err:
                await oauth_client(reply(terminal)).poll("dc")
            assert err.value.error == terminal

    async def test_a_bare_401_is_the_agent_jwt_being_refused_not_an_oauth_error_code(self):
        with pytest.raises(OAuthError) as err:
            await oauth_client(lambda r: httpx.Response(401, json={"error": "invalid_client"})).poll("dc")
        assert err.value.error == "http_error"

    async def test_token_scope_is_what_the_user_approved_which_may_be_less(self):
        body = {"token_type": "Bearer", "access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "orders:read"}
        token = await oauth_client(lambda r: httpx.Response(200, json=body)).poll("dc")
        assert isinstance(token, DelegationToken)
        assert token.scopes == ["orders:read"] and token.expires_at == 4600.0
        assert token.usable(now=1000) and not token.usable(now=4590)

    async def test_wait_polls_at_the_interval_and_adds_five_seconds_on_slow_down(self):
        answers = iter([("authorization_pending", 400), ("slow_down", 400), ("ok", 200)])
        slept = []

        def handler(request):
            kind, status = next(answers)
            if kind == "ok":
                return httpx.Response(200, json={"access_token": "at", "expires_in": 3600, "scope": "orders:read"})
            return httpx.Response(status, json={"error": kind})

        async def sleep(seconds):
            slept.append(seconds)

        clock = {"t": 1000.0}
        c = oauth_client(handler, now=lambda: clock["t"])
        auth = DeviceAuthorization("dc", "U", "https://b", "https://b?c", expires_at=2000.0, interval=5)
        token = await c.wait(auth, sleep)
        assert token.access_token == "at"
        assert slept == [5, 5, 10]

    async def test_wait_gives_up_when_the_code_expires(self):
        c = oauth_client(lambda r: pytest.fail("no time left to poll"), now=lambda: 1000.0)
        with pytest.raises(OAuthError) as err:
            await c.wait(DeviceAuthorization("dc", "U", "u", "u", expires_at=1003.0, interval=5), lambda s: None)
        assert err.value.error == "expired_token"

    async def test_refresh_uses_the_refresh_grant(self):
        seen = {}

        def handler(request):
            seen.update(dict(httpx.QueryParams(request.content.decode())))
            return httpx.Response(200, json={"access_token": "at2", "refresh_token": "rt2", "expires_in": 3600, "scope": "orders:read"})

        token = await oauth_client(handler).refresh("rt1")
        assert seen == {"grant_type": "refresh_token", "refresh_token": "rt1", "client_id": ISSUER}
        assert token.refresh_token == "rt2"


def message_reply(receipt=None):
    metadata = {"pact.receipt": receipt} if receipt else {}
    return {"message": {"messageId": "r", "contextId": "ctx-1", "role": "ROLE_AGENT", "parts": [{"text": "Order ord-1"}], "metadata": metadata}}


STEP_UP = {"task": {"id": "t-1", "contextId": "ctx-1", "status": {"state": "TASK_STATE_AUTH_REQUIRED", "message": {"parts": [{"text": "I need permission to view the customer's orders."}]}},
                    "metadata": {"pact.missingScopes": ["orders:read"], "pact.verificationUriComplete": "https://b/pact/login?return_to=x"}}}


def pact_client(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PactClient("https://p.example/a2a/01", lambda: "agent.jwt", http=http)


class TestSendDelegated:
    async def test_a_step_up_task_comes_back_as_auth_required_with_the_link(self):
        result = await pact_client(lambda r: httpx.Response(200, json=STEP_UP)).send_delegated("where is my order")
        assert isinstance(result, AuthRequired)
        assert result.context_id == "ctx-1" and result.missing_scopes == ["orders:read"]
        assert result.verification_uri_complete == "https://b/pact/login?return_to=x"
        assert "permission" in result.text

    async def test_the_delegation_token_travels_in_its_own_header_beside_the_agent_jwt(self):
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx.Response(200, json=message_reply())

        await pact_client(handler).send_delegated("hi", context_id="ctx-1", delegation_token="deleg.tok")
        assert seen["authorization"] == "Bearer agent.jwt"
        assert seen["x-a2a-user-delegation"] == "Bearer deleg.tok"

    async def test_no_delegation_header_when_there_is_no_token(self):
        seen = {}
        await pact_client(lambda r: seen.update(r.headers) or httpx.Response(200, json=message_reply())).send_delegated("hi")
        assert "x-a2a-user-delegation" not in seen

    async def test_the_receipt_is_returned_with_the_reply(self):
        receipt = {"jws": "a.b.c", "claims": {"user": "auth0|1"}}
        result = await pact_client(lambda r: httpx.Response(200, json=message_reply(receipt))).send_delegated("hi", delegation_token="t")
        assert isinstance(result, PactReply) and result.receipt == receipt

    async def test_an_unexpected_task_state_is_an_error_not_a_guess(self):
        task = {"task": {"id": "t", "contextId": "c", "status": {"state": "TASK_STATE_WORKING"}}}
        with pytest.raises(PactError):
            await pact_client(lambda r: httpx.Response(200, json=task)).send_delegated("hi")

    @pytest.mark.parametrize("header", ["www-authenticate", "x-amzn-remapped-www-authenticate"])
    async def test_a_refused_delegation_token_is_recognised_under_either_header_name(self, header):
        # Lambda Function URLs rename WWW-Authenticate; the client must not depend on the original name.
        response = httpx.Response(401, headers={header: 'Bearer realm="a2a", error="invalid_token"'})
        with pytest.raises(PactHttpError) as err:
            await pact_client(lambda r: response).send_delegated("hi", delegation_token="t")
        assert err.value.token_rejected

    async def test_a_refused_agent_jwt_is_not_mistaken_for_a_refused_delegation_token(self):
        with pytest.raises(PactHttpError) as err:
            await pact_client(lambda r: httpx.Response(401, headers={"www-authenticate": 'Bearer realm="a2a"'})).send_delegated("hi")
        assert not err.value.token_rejected


def b64(n):
    return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()


@pytest.fixture
def signer():
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1()).private_numbers()
    private = {"kty": "EC", "crv": "P-256", "x": b64(key.public_numbers.x), "y": b64(key.public_numbers.y), "d": b64(key.private_value)}
    public = {k: private[k] for k in ("kty", "crv", "x", "y")} | {"kid": "k1", "alg": "ES256", "use": "sig"}
    return private, {"keys": [public]}


def make_receipt(private, claims):
    token = jws.sign(json.dumps(claims, separators=(",", ":")).encode(), private, algorithm="ES256", headers={"kid": "k1", "typ": "pact-receipt+jws"})
    return {"jws": token, "claims": claims}


CLAIMS = {"grantId": "a2agrant_1", "user": "auth0|1", "pa": ISSUER, "brand": "https://p.example/a2a/01",
          "scopesUsed": ["orders:read"], "actions": [{"tool": "list_orders"}], "ts": "2026-10-20T12:00:00Z"}


class TestReceipts:
    def test_a_genuine_receipt_verifies_and_returns_the_signed_claims(self, signer):
        private, jwks = signer
        assert verify_receipt(make_receipt(private, CLAIMS), jwks) == CLAIMS

    def test_expected_claims_are_enforced(self, signer):
        private, jwks = signer
        receipt = make_receipt(private, CLAIMS)
        assert verify_receipt(receipt, jwks, {"pa": ISSUER, "user": "auth0|1"})
        with pytest.raises(ReceiptError):
            verify_receipt(receipt, jwks, {"user": "auth0|someone-else"})

    def test_plain_claims_edited_after_signing_are_caught(self, signer):
        private, jwks = signer
        receipt = make_receipt(private, CLAIMS)
        receipt["claims"] = {**CLAIMS, "scopesUsed": ["orders:read", "orders:cancel"]}
        with pytest.raises(ReceiptError):
            verify_receipt(receipt, jwks)

    def test_a_signature_from_another_key_is_rejected(self, signer):
        _, jwks = signer
        from cryptography.hazmat.primitives.asymmetric import ec
        k = ec.generate_private_key(ec.SECP256R1()).private_numbers()
        forger = {"kty": "EC", "crv": "P-256", "x": b64(k.public_numbers.x), "y": b64(k.public_numbers.y), "d": b64(k.private_value)}
        with pytest.raises(ReceiptError):
            verify_receipt(make_receipt(forger, CLAIMS), jwks)

    def test_an_unknown_kid_and_a_missing_jws_are_rejected(self, signer):
        private, jwks = signer
        with pytest.raises(ReceiptError):
            verify_receipt(make_receipt(private, CLAIMS), {"keys": []})
        with pytest.raises(ReceiptError):
            verify_receipt({"claims": CLAIMS}, jwks)
