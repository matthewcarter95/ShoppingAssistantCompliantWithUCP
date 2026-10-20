#!/usr/bin/env python3
"""Register this assistant with a PACT Provider and run one real exchange, including step-up.

    AWS_PROFILE=btaws python scripts/pact_live_exchange.py --provider https://smitty-api.demo-connect.us \\
        --question "Where is my latest order?" [--register-only]

Signs with the production key from SSM (never printed). Needs a person for one step: open the
printed link, sign in with the Brand, and approve. Run from a directory without a .env file.
"""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "unused")  # Settings requires it; nothing here calls OpenAI
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from src.chatbot.config import settings  # noqa: E402
from src.chatbot.pact.client import AuthRequired, PactClient, PactHttpError, fetch_agent_card, interface_url  # noqa: E402
from src.chatbot.pact.delegation import DeviceCodeClient, delegation_scheme, fetch_jwks_for, verify_receipt  # noqa: E402
from src.chatbot.pact.signer import opaque_sub, sign_pact_jwt  # noqa: E402


def say(msg: str) -> None:
    print(msg, flush=True)


async def register(provider: str, name: str, issuer: str) -> None:
    url = f"{provider}/api/platforms"
    token = sign_pact_jwt(issuer, url, ttl_seconds=120)  # sub = iss, aud = the registration endpoint
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(url, json={"name": name, "jwksUri": f"{issuer}/.well-known/jwks.json"},
                            headers={"Authorization": f"Bearer {token}"})
    say(f"register: HTTP {r.status_code} {r.text[:200]}")
    if r.status_code not in (200, 201):
        raise SystemExit("registration failed")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True)
    ap.add_argument("--audience", help="defaults to <provider>/a2a")
    ap.add_argument("--name", default="shopping-assistant")
    ap.add_argument("--question", default="Where is my latest order?")
    ap.add_argument("--user", default="live-exchange-user", help="stands in for the assistant's own user id")
    ap.add_argument("--register-only", action="store_true")
    ap.add_argument("--wait", type=int, default=540, help="seconds to wait for the person to approve")
    args = ap.parse_args()

    provider = args.provider.rstrip("/")
    audience = args.audience or f"{provider}/a2a"
    issuer = settings.pact_issuer_url
    say(f"issuer: {issuer}\naudience: {audience}")

    await register(provider, args.name, issuer)
    if args.register_only:
        return

    sub = opaque_sub(args.user)
    get_token = lambda: sign_pact_jwt(sub, audience)  # a fresh JWT for every request
    card = await fetch_agent_card(f"{provider}/.well-known/agent-card.json")
    iface = interface_url(card)
    scheme = delegation_scheme(card)
    say(f"brand: {card['name']}  interface: {iface}\nsub: {sub}  delegation offered: {bool(scheme)}")
    if scheme is None:
        raise SystemExit("the Brand does not offer delegation")
    client = PactClient(iface, get_token)

    say("\n1) identity-only message")
    hello = await client.send_delegated("What are your store hours?")
    say(f"   -> {type(hello).__name__}: {getattr(hello, 'text', '')[:120]!r}  receipt: {getattr(hello, 'receipt', None) is not None}")

    say(f"\n2) {args.question!r} with no delegation token")
    first = await client.send_delegated(args.question)
    if not isinstance(first, AuthRequired):
        raise SystemExit(f"expected a step-up task, got {first!r}")
    say(f"   -> AUTH_REQUIRED, missing {first.missing_scopes}, context {first.context_id}")
    say(f"      {first.text}")

    say("\n3) device authorization for the missing scopes")
    oauth = DeviceCodeClient(scheme, issuer, get_token)
    auth = await oauth.start(first.missing_scopes)
    say(f"\n>>> OPEN THIS LINK, sign in to Dollar Treasure, and click Allow:\n>>> {auth.verification_uri_complete}\n")

    deadline = min(auth.expires_at, time.time() + args.wait)
    interval = auth.interval
    token = None
    while time.time() + interval <= deadline:
        await asyncio.sleep(interval)
        result = await oauth.poll(auth.device_code)
        if result == "slow_down":
            interval += 5
        elif result != "pending":
            token = result
            break
    if token is None:
        raise SystemExit("timed out waiting for approval")
    say(f"4) approved. scopes granted: {token.scopes}  expires in {int(token.expires_at - time.time())}s")

    say("\n5) same conversation, now with the delegation token")
    second = await client.send_delegated(args.question, context_id=first.context_id, delegation_token=token.access_token)
    if isinstance(second, AuthRequired):
        raise SystemExit(f"still asked for step-up: {second.missing_scopes}")
    say(f"   context kept: {second.context_id == first.context_id}\n   reply: {second.text}")

    say("\n6) receipt")
    if not second.receipt:
        raise SystemExit("no receipt on a delegated reply")
    jwks = await fetch_jwks_for(scheme.metadata_url)
    claims = verify_receipt(second.receipt, jwks, {"pa": issuer, "brand": iface})
    say(f"   verified against the Brand's published key: {claims}")

    say("\n7) refresh token rotation")
    if token.refresh_token:
        newer = await oauth.refresh(token.refresh_token)
        say(f"   refreshed ok, new token differs: {newer.access_token != token.access_token}")
        try:
            await oauth.refresh(token.refresh_token)
            say("   !! the old refresh token still worked")
        except Exception as e:  # noqa: BLE001
            say(f"   old refresh token rejected: {e}")

    say("\nDONE")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except PactHttpError as e:
        raise SystemExit(f"HTTP {e.http_status} {e.www_authenticate}")
