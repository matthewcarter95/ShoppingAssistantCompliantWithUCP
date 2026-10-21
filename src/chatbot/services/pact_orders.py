"""check_orders: ask the merchant's own agent about the shopper's orders over PACT.

Two rules shape this module:
  - What comes back is another system's text. It is cleaned, length-capped, and shown to the
    shopper as-is; the model never sees it, so nothing in it can steer the assistant's tools.
  - A reply obtained with a delegation token is only shown if the merchant's signed receipt
    verifies and agrees with what we asked for. Without that, we say so and show nothing.
"""
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from jose import jwt

from ..config import settings
from ..pact.client import AuthRequired, PactClient, PactError, PactHttpError, PactReply, fetch_agent_card, interface_url
from ..pact.delegation import (
    DelegationScheme,
    DelegationToken,
    DeviceCodeClient,
    OAuthError,
    ReceiptError,
    delegation_scheme,
    fetch_jwks_for,
    verify_receipt,
)
from ..pact.keys import pact_enabled
from ..pact.signer import opaque_sub, sign_pact_jwt
from ..utils.logger import setup_logger

logger = setup_logger(__name__, settings.log_level)

CARD_TTL_SECONDS = 300
MAX_REPLY_CHARS = 1500
MAX_QUESTION_CHARS = 500
MAX_RECEIPTS = 20
# What chat history keeps instead of the merchant's text.
ORDERS_SHOWN = "(I showed the shopper the order details the merchant sent back.)"
GENERIC_ERROR = "I couldn't reach the merchant's order lookup just now. Please try again in a moment."


@dataclass
class Outcome:
    """kind: reply | step_up | pending | denied | expired | none | error"""

    kind: str
    text: str = ""
    auth_url: Optional[str] = None
    interval: int = 5


@dataclass
class _Brand:
    name: str
    interface: str
    scheme: Optional[DelegationScheme]
    fetched: float
    jwks: Optional[Dict[str, Any]] = None


def clean_reply(text: Any) -> str:
    """Printable text only, at most MAX_REPLY_CHARS. The frontend also renders it as plain text."""
    cleaned = "".join(ch for ch in str(text) if ch == "\n" or (ch >= " " and ch != "\x7f")).strip()
    if len(cleaned) > MAX_REPLY_CHARS:
        cleaned = cleaned[: MAX_REPLY_CHARS - 1].rstrip() + "…"
    return cleaned or "The merchant sent an empty reply."


def safe_auth_url(url: Any, allow_insecure: bool = False) -> Optional[str]:
    """The sign-in link comes from the merchant's Provider. Open it only if it is plain https."""
    try:
        parsed = urlparse(str(url))
    except ValueError:
        return None
    if not parsed.hostname or parsed.username or parsed.password:
        return None
    local = parsed.hostname in ("localhost", "127.0.0.1")
    if parsed.scheme == "https" or (parsed.scheme == "http" and local and allow_insecure):
        return parsed.geturl()
    return None


def _token_to_dict(t: DelegationToken) -> Dict[str, Any]:
    return {"access_token": t.access_token, "refresh_token": t.refresh_token, "scopes": list(t.scopes),
            "expires_at": int(t.expires_at)}


def _token_from_dict(d: Dict[str, Any]) -> DelegationToken:
    return DelegationToken(d["access_token"], d.get("refresh_token"), list(d.get("scopes", [])), float(d["expires_at"]))


class PactOrders:
    def __init__(self, *, card_url: str, audience: str, issuer: str, http: Optional[httpx.AsyncClient] = None,
                 now: Callable[[], float] = time.time, sub_fn: Callable[[str], str] = opaque_sub,
                 sign_fn: Callable[..., str] = sign_pact_jwt, allow_insecure: bool = False):
        self.card_url = card_url
        self.audience = audience
        self.issuer = issuer
        self._http = http
        self._now = now
        self._sub_fn = sub_fn
        self._sign = sign_fn
        self._allow_insecure = allow_insecure
        self._brand_cache: Optional[_Brand] = None

    @property
    def enabled(self) -> bool:
        return bool(self.card_url and self.audience and pact_enabled())

    # ---- discovery ----

    async def _brand(self) -> _Brand:
        cached = self._brand_cache
        if cached and self._now() < cached.fetched + CARD_TTL_SECONDS:
            return cached
        card = await fetch_agent_card(self.card_url, self._http)
        self._brand_cache = _Brand(name=str(card.get("name") or "the merchant"), interface=interface_url(card),
                                   scheme=delegation_scheme(card), fetched=self._now())
        return self._brand_cache

    def _clients(self, brand: _Brand, auth0_sub: str):
        # A fresh JWT for every request. `sub` is opaque: never the shopper's email.
        get_token = lambda: self._sign(self._sub_fn(auth0_sub), self.audience)  # noqa: E731
        client = PactClient(brand.interface, get_token, http=self._http)
        oauth = DeviceCodeClient(brand.scheme, self.issuer, get_token, http=self._http, now=self._now) if brand.scheme else None
        return client, oauth

    # ---- asking ----

    async def ask(self, state, auth0_sub: str, question: str) -> Outcome:
        try:
            brand = await self._brand()
            if brand.scheme is None:
                return Outcome("error", f"{brand.name} doesn't let assistants look up orders.")
            return await self._exchange(state, auth0_sub, brand, question.strip()[:MAX_QUESTION_CHARS] or "Where are my orders?")
        except Exception:  # noqa: BLE001 - never leak details of a merchant failure into the chat
            logger.error("check_orders failed", exc_info=True)
            return Outcome("error", GENERIC_ERROR)

    async def _usable_token(self, pact: Dict[str, Any], oauth: DeviceCodeClient) -> Optional[DelegationToken]:
        raw = pact.get("token")
        if not raw:
            return None
        token = _token_from_dict(raw)
        if token.usable(self._now()):
            return token
        if token.refresh_token:
            try:
                fresh = await oauth.refresh(token.refresh_token)
                pact["token"] = _token_to_dict(fresh)
                return fresh
            except OAuthError:
                logger.info("Refresh token no longer works; asking the shopper again")
        pact.pop("token", None)
        return None

    async def _exchange(self, state, auth0_sub: str, brand: _Brand, question: str) -> Outcome:
        pact = state.pact = state.pact or {}
        client, oauth = self._clients(brand, auth0_sub)
        dropped_token = dropped_context = False
        result: Any = None
        token: Optional[DelegationToken] = None
        for _ in range(3):
            token = await self._usable_token(pact, oauth)
            try:
                result = await client.send_delegated(
                    question, context_id=pact.get("context_id"),
                    delegation_token=token.access_token if token else None)
                break
            except PactHttpError as e:
                if e.token_rejected and token and not dropped_token:
                    pact.pop("token", None)  # revoked or expired upstream: ask the shopper again
                    dropped_token = True
                    continue
                raise
            except PactError as e:
                if pact.get("context_id") and e.reason in ("INVALID_PARAMS", "UNSUPPORTED_OPERATION") and not dropped_context:
                    pact.pop("context_id", None)  # the merchant closed or forgot the conversation
                    dropped_context = True
                    continue
                raise
        if result is None:
            raise RuntimeError("merchant kept refusing the request")

        if isinstance(result, AuthRequired):
            return await self._step_up(pact, oauth, brand, result, token, question)

        pact["context_id"] = result.context_id
        if token is not None:
            try:
                await self._check_receipt(pact, brand, token, result)
            except ReceiptError as e:
                logger.error(f"Rejecting merchant reply: {e}")
                return Outcome("error", "I couldn't verify the merchant's record of that lookup, so I'm not showing the result.")
        return Outcome("reply", clean_reply(result.text))

    async def _step_up(self, pact, oauth, brand: _Brand, needed: AuthRequired, token: Optional[DelegationToken],
                       question: str) -> Outcome:
        pact["context_id"] = needed.context_id or pact.get("context_id")
        # Keep what the shopper already allowed: the new token replaces the old one.
        wanted = list(dict.fromkeys((token.scopes if token else []) + needed.missing_scopes))
        try:
            auth = await oauth.start(wanted)
        except ValueError:
            return Outcome("error", f"{brand.name} asked for a permission I can't request.")
        url = safe_auth_url(auth.verification_uri_complete, self._allow_insecure)
        if url is None:
            logger.error("Refusing a sign-in link that is not https")
            return Outcome("error", f"{brand.name} sent a sign-in link I don't trust, so I didn't open it.")
        pact["pending"] = {
            "device_code": auth.device_code, "expires_at": int(auth.expires_at), "interval": auth.interval,
            "next_poll_ms": int((self._now() + auth.interval) * 1000), "scopes": wanted, "question": question,
        }
        host = urlparse(url).hostname
        return Outcome("step_up", f"To look up your orders, {brand.name} needs your permission. Sign in at {host} and "
                       "choose what I can see. I never see your password.", auth_url=url, interval=auth.interval)

    async def _check_receipt(self, pact, brand: _Brand, token: DelegationToken, reply: PactReply) -> None:
        if not reply.receipt:
            raise ReceiptError("A reply under a delegation token carried no receipt")
        grant_id = jwt.get_unverified_claims(token.access_token).get("grant_id")
        expected = {"pa": self.issuer, "brand": brand.interface, **({"grantId": grant_id} if grant_id else {})}
        claims = None
        for attempt in range(2):  # a rotated Brand key shows up as an unknown kid: refetch once
            if brand.jwks is None or attempt:
                brand.jwks = await fetch_jwks_for(brand.scheme.metadata_url, self._http)
            try:
                claims = verify_receipt(reply.receipt, brand.jwks, expected)
                break
            except ReceiptError:
                if attempt:
                    raise
        extra = set(claims["scopesUsed"]) - set(token.scopes)
        if extra:
            raise ReceiptError(f"Receipt claims scopes the shopper did not grant: {sorted(extra)}")
        kept = pact.setdefault("receipts", [])
        kept.append({"grant_id": claims["grantId"], "ts": claims["ts"], "scopes_used": claims["scopesUsed"],
                     "actions": [a.get("tool") for a in claims["actions"]]})
        pact["receipts"] = kept[-MAX_RECEIPTS:]

    # ---- waiting for the shopper ----

    async def resume(self, state, auth0_sub: str) -> Outcome:
        """One poll of the pending device code; on approval, asks the stored question again."""
        pact = state.pact or {}
        pending = pact.get("pending")
        if not pending:
            return Outcome("none")
        now = self._now()
        interval = int(pending.get("interval", 5))
        if now >= float(pending["expires_at"]):
            pact.pop("pending", None)
            return Outcome("expired", "The approval request timed out. Ask me again and I'll start a new one.")
        if now * 1000 < float(pending.get("next_poll_ms", 0)):
            return Outcome("pending", interval=interval)  # too soon: don't poll the merchant, don't risk slow_down
        try:
            brand = await self._brand()
            _, oauth = self._clients(brand, auth0_sub)
            polled = await oauth.poll(pending["device_code"])
        except OAuthError as e:
            pact.pop("pending", None)
            if e.error == "access_denied":
                return Outcome("denied", "No problem. I didn't get access to your orders.")
            if e.error == "expired_token":
                return Outcome("expired", "The approval request timed out. Ask me again and I'll start a new one.")
            logger.error(f"Device authorization failed: {e}")
            return Outcome("error", GENERIC_ERROR)
        except Exception:  # noqa: BLE001
            logger.error("Polling the merchant failed", exc_info=True)
            return Outcome("pending", interval=interval)  # transient: the frontend tries again

        if not isinstance(polled, DelegationToken):
            if polled == "slow_down":
                interval += 5  # RFC 8628 §3.5
            pending.update(interval=interval, next_poll_ms=int((now + interval) * 1000))
            state.pact = pact
            return Outcome("pending", interval=interval)

        pact["token"] = _token_to_dict(polled)
        question = pending.get("question") or "Where are my orders?"
        pact.pop("pending", None)
        return await self.ask(state, auth0_sub, question)


_instance: Optional[PactOrders] = None


def get_pact_orders() -> PactOrders:
    global _instance
    if _instance is None:
        _instance = PactOrders(card_url=settings.pact_brand_card_url, audience=settings.pact_audience,
                               issuer=settings.pact_issuer_url, allow_insecure=settings.ucp_allow_insecure)
    return _instance
