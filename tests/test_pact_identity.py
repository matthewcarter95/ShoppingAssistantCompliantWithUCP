"""PACT Identity (personal-agent side): signed JWT, opaque sub, JWKS route, A2A client."""
import json
import time

import httpx
import pytest
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError

from src.chatbot.config import settings
from src.chatbot.pact import keys as pact_keys
from src.chatbot.pact.client import (
    PactClient,
    PactError,
    PactHttpError,
    fetch_agent_card,
    interface_url,
)
from src.chatbot.pact.keys import PactNotConfigured, parse_private_jwk, read_secret, thumbprint
from src.chatbot.pact.signer import opaque_sub, sign_pact_jwt

ISSUER = "https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws"
AUDIENCE = "https://provider.example/a2a"


def _private_jwk() -> str:
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec

    def b64(n):
        return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()

    k = ec.generate_private_key(ec.SECP256R1()).private_numbers()
    return json.dumps({"kty": "EC", "crv": "P-256", "x": b64(k.public_numbers.x),
                       "y": b64(k.public_numbers.y), "d": b64(k.private_value)})


@pytest.fixture
def key():
    return parse_private_jwk(_private_jwk())


def verify_like_a_provider(token, key, *, audience=AUDIENCE, issuer=ISSUER):
    """What spec §3.2 says a Provider does: ES256 only, signature via our JWKS, iss/aud/exp."""
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "ES256"
    return jwt.decode(token, key.public_jwk, algorithms=["ES256"], audience=audience, issuer=issuer)


class TestSignedJwt:
    def test_has_every_claim_the_spec_requires(self, key):
        token = sign_pact_jwt("u_abc", AUDIENCE, key=key, issuer=ISSUER)
        claims = verify_like_a_provider(token, key)
        assert claims["iss"] == ISSUER
        assert claims["sub"] == "u_abc"
        assert claims["aud"] == AUDIENCE  # one string, verbatim
        assert claims["jti"]
        assert 0 < claims["exp"] - claims["iat"] <= 300
        assert jwt.get_unverified_header(token)["kid"] == key.kid

    def test_default_lifetime_is_120_seconds(self, key):
        claims = verify_like_a_provider(sign_pact_jwt("u", AUDIENCE, key=key, issuer=ISSUER), key)
        assert claims["exp"] - claims["iat"] == 120

    @pytest.mark.parametrize("ttl", [0, -1, 301, 3600])
    def test_refuses_lifetimes_the_spec_forbids(self, key, ttl):
        with pytest.raises(ValueError):
            sign_pact_jwt("u", AUDIENCE, key=key, issuer=ISSUER, ttl_seconds=ttl)

    @pytest.mark.parametrize("sub,aud", [("", AUDIENCE), ("u", "")])
    def test_requires_sub_and_audience(self, key, sub, aud):
        with pytest.raises(ValueError):
            sign_pact_jwt(sub, aud, key=key, issuer=ISSUER)

    def test_rejected_for_wrong_audience_issuer_key_or_age(self, key):
        token = sign_pact_jwt("u", AUDIENCE, key=key, issuer=ISSUER)
        with pytest.raises(JWTClaimsError):
            verify_like_a_provider(token, key, audience="https://other.example/a2a")
        with pytest.raises(JWTClaimsError):
            verify_like_a_provider(token, key, issuer="https://evil.example")
        with pytest.raises(JWTError):
            verify_like_a_provider(token, parse_private_jwk(_private_jwk()))
        old = sign_pact_jwt("u", AUDIENCE, key=key, issuer=ISSUER, now=int(time.time()) - 600)
        with pytest.raises(ExpiredSignatureError):
            verify_like_a_provider(old, key)

    def test_each_token_is_unique(self, key):
        a = sign_pact_jwt("u", AUDIENCE, key=key, issuer=ISSUER)
        b = sign_pact_jwt("u", AUDIENCE, key=key, issuer=ISSUER)
        assert jwt.get_unverified_claims(a)["jti"] != jwt.get_unverified_claims(b)["jti"]

    def test_default_issuer_is_the_function_url(self, key, monkeypatch):
        monkeypatch.setattr(settings, "pact_issuer", "")
        token = sign_pact_jwt("u", AUDIENCE, key=key)
        assert jwt.get_unverified_claims(token)["iss"] == settings.chatbot_base_url.rstrip("/") == ISSUER


class TestOpaqueSub:
    def test_stable_per_user_and_secret(self):
        assert opaque_sub("auth0|123", "s3cret") == opaque_sub("auth0|123", "s3cret")

    def test_differs_by_user_and_by_secret(self):
        assert opaque_sub("auth0|123", "s3cret") != opaque_sub("auth0|456", "s3cret")
        assert opaque_sub("auth0|123", "s3cret") != opaque_sub("auth0|123", "other")

    def test_contains_no_personal_data(self):
        sub = opaque_sub("auth0|matt@example.com", "s3cret")
        assert "matt" not in sub and "example" not in sub and "auth0" not in sub
        assert sub.startswith("u_") and len(sub) == 26

    def test_requires_a_subject(self):
        with pytest.raises(ValueError):
            opaque_sub("", "s3cret")


class TestKeys:
    def test_public_jwk_never_leaks_the_private_part(self, key):
        assert "d" not in key.public_jwk
        assert key.public_jwk["kid"] == key.kid == thumbprint(key.public_jwk)
        assert key.public_jwk["alg"] == "ES256" and key.public_jwk["use"] == "sig"

    @pytest.mark.parametrize("bad", [
        json.dumps({"kty": "RSA", "n": "x", "e": "AQAB"}),
        json.dumps({"kty": "EC", "crv": "P-384", "x": "a", "y": "b", "d": "c"}),
        json.dumps({"kty": "EC", "crv": "P-256", "x": "a", "y": "b"}),  # public only
    ])
    def test_rejects_anything_but_a_private_p256_key(self, bad):
        with pytest.raises(ValueError):
            parse_private_jwk(bad)

    def test_secret_comes_from_ssm_when_not_given_directly(self):
        asked = []
        reader = lambda name: asked.append(name) or "from-ssm"
        assert read_secret("", "/shopping-assistant/pact/private-jwk", reader) == "from-ssm"
        assert asked == ["/shopping-assistant/pact/private-jwk"]
        assert read_secret("direct", "/x", reader) == "direct" and len(asked) == 1
        assert read_secret("", "", reader) is None

    def test_missing_configuration_is_reported_not_guessed(self, monkeypatch):
        monkeypatch.setattr(pact_keys, "_cached_key", None)
        monkeypatch.setattr(settings, "pact_private_jwk", "")
        monkeypatch.setattr(settings, "pact_key_ssm_parameter", "")
        with pytest.raises(PactNotConfigured):
            pact_keys.get_pact_key()


class TestJwksRoute:
    @pytest.fixture
    def web(self, monkeypatch, tmp_path):
        # auth/config.py reads ./.env and rejects keys it doesn't declare, so import the
        # real app (and check the router is mounted on it) from a directory with no .env.
        from fastapi.testclient import TestClient

        monkeypatch.chdir(tmp_path)
        from src.chatbot.app import app
        return TestClient(app)

    def test_404_while_pact_is_off(self, web, monkeypatch):
        monkeypatch.setattr(settings, "pact_private_jwk", "")
        monkeypatch.setattr(settings, "pact_key_ssm_parameter", "")
        assert web.get("/.well-known/jwks.json").status_code == 404

    def test_serves_only_the_public_key(self, web, monkeypatch):
        raw = _private_jwk()
        monkeypatch.setattr(settings, "pact_private_jwk", raw)
        monkeypatch.setattr(pact_keys, "_cached_key", None)
        response = web.get("/.well-known/jwks.json")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=300"
        keys = response.json()["keys"]
        assert len(keys) == 1 and "d" not in keys[0]
        assert keys[0]["x"] == json.loads(raw)["x"]
        assert json.loads(raw)["d"] not in response.text
        monkeypatch.setattr(pact_keys, "_cached_key", None)


CARD = {"supportedInterfaces": [
    {"url": "https://old.example/a2a/1", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"},
    {"url": "https://provider.example/a2a/01DT/", "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"},
]}


def reply(context="ctx-1", text="Sure, what is the order number?"):
    return {"message": {"messageId": "r-1", "contextId": context, "role": "ROLE_AGENT", "parts": [{"text": text}]}}


def client_with(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PactClient("https://provider.example/a2a/01DT/", lambda: "tok", http=http)


class TestAgentCard:
    def test_interface_is_chosen_by_binding_and_version_not_position(self):
        assert interface_url(CARD) == "https://provider.example/a2a/01DT"

    def test_no_usable_interface_is_an_error(self):
        with pytest.raises(ValueError):
            interface_url({"supportedInterfaces": [{"url": "x", "protocolBinding": "GRPC", "protocolVersion": "1.0"}]})

    async def test_fetch_sends_no_credentials_and_maps_404(self):
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx.Response(404)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(PactHttpError) as err:
                await fetch_agent_card("https://provider.example/a2a/nope/.well-known/agent-card.json", http)
        assert err.value.http_status == 404 and "authorization" not in seen


class TestSendMessage:
    async def test_posts_the_spec_request_and_returns_context(self):
        seen = {}

        def handler(request):
            seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, json.loads(request.content)
            return httpx.Response(200, json=reply())

        result = await client_with(handler).send_message("I need help with my order.")
        assert seen["url"] == "https://provider.example/a2a/01DT/message:send"
        assert seen["headers"]["authorization"] == "Bearer tok"
        assert seen["headers"]["a2a-version"] == "1.0"
        message = seen["body"]["message"]
        assert message["role"] == "ROLE_USER" and message["messageId"] and "contextId" not in message
        assert message["parts"][0]["text"] == "I need help with my order."
        assert (result.text, result.context_id) == ("Sure, what is the order number?", "ctx-1")

    async def test_continues_a_conversation_and_allows_safe_retry(self):
        bodies = []

        def handler(request):
            bodies.append(json.loads(request.content)["message"])
            return httpx.Response(200, json=reply())

        c = client_with(handler)
        await c.send_message("Order 4471", context_id="ctx-1", message_id="m-fixed")
        await c.send_message("Order 4471", context_id="ctx-1", message_id="m-fixed")
        assert [b["contextId"] for b in bodies] == ["ctx-1", "ctx-1"]
        assert bodies[0]["messageId"] == bodies[1]["messageId"] == "m-fixed"

    async def test_a_fresh_jwt_is_requested_for_every_message(self):
        tokens = iter(["t1", "t2"])
        sent = []

        def handler(request):
            sent.append(request.headers["authorization"])
            return httpx.Response(200, json=reply())

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        c = PactClient("https://provider.example/a2a/01DT", lambda: next(tokens), http=http)
        await c.send_message("a")
        await c.send_message("b")
        assert sent == ["Bearer t1", "Bearer t2"]

    async def test_blank_text_never_leaves_the_process(self):
        with pytest.raises(ValueError):
            await client_with(lambda r: pytest.fail("should not send")).send_message("   ")

    async def test_reads_the_reason_from_the_envelope_not_the_status(self):
        envelope = {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "Unknown contextId",
                              "details": [{"reason": "INVALID_PARAMS", "domain": "a2a-protocol.org"}]}}
        with pytest.raises(PactError) as err:
            await client_with(lambda r: httpx.Response(400, json=envelope)).send_message("hi", context_id="x")
        assert err.value.reason == "INVALID_PARAMS" and err.value.http_status == 400

    async def test_closed_conversation_is_distinguishable(self):
        envelope = {"error": {"code": 400, "status": "FAILED_PRECONDITION", "message": "closed",
                              "details": [{"reason": "UNSUPPORTED_OPERATION"}]}}
        with pytest.raises(PactError) as err:
            await client_with(lambda r: httpx.Response(400, json=envelope)).send_message("hi", context_id="x")
        assert err.value.reason == "UNSUPPORTED_OPERATION"

    @pytest.mark.parametrize("status,retry,expected", [(401, None, None), (429, "7", 7.0), (404, None, None)])
    async def test_bare_http_failures_carry_retry_after(self, status, retry, expected):
        headers = {"Retry-After": retry} if retry else {}
        with pytest.raises(PactHttpError) as err:
            await client_with(lambda r: httpx.Response(status, headers=headers)).send_message("hi")
        assert err.value.http_status == status and err.value.retry_after == expected

    async def test_identity_send_refuses_a_step_up_task(self):
        task = {"task": {"id": "t-1", "contextId": "ctx", "status": {"state": "TASK_STATE_AUTH_REQUIRED"}}}
        with pytest.raises(PactError) as err:
            await client_with(lambda r: httpx.Response(200, json=task)).send_message("my orders")
        assert err.value.reason == "UNSUPPORTED_RESPONSE"
