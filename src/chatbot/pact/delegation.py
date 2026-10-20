"""PACT Delegated client (spec §5): device-code OAuth with the personal-agent JWT as the client
credential, delegation tokens, and signed receipts. The User logs in with the Brand, never here."""
import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

import httpx
from jose import jws
from jose.exceptions import JWSError

DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class OAuthError(Exception):
    """RFC 6749 §5.2 / RFC 8628 error. `error` is the machine-readable code."""

    def __init__(self, http_status: int, error: str, description: str = ""):
        super().__init__(f"{error}: {description}" if description else error)
        self.http_status = http_status
        self.error = error
        self.description = description


class ReceiptError(Exception):
    pass


@dataclass(frozen=True)
class DelegationScheme:
    device_authorization_url: str
    token_url: str
    metadata_url: str
    scopes: Dict[str, str]


@dataclass(frozen=True)
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_at: float
    interval: int


@dataclass(frozen=True)
class DelegationToken:
    access_token: str
    refresh_token: Optional[str]
    scopes: List[str]
    expires_at: float

    def usable(self, now: float, skew: float = 30) -> bool:
        return now + skew < self.expires_at


def delegation_scheme(card: Dict[str, Any]) -> Optional[DelegationScheme]:
    """Find the card's requirement that pairs the agent JWT with an OAuth2 device-code scheme (spec §5.1)."""
    schemes = card.get("securitySchemes") or {}
    for requirement in card.get("securityRequirements") or []:
        names = list((requirement.get("schemes") or {}).keys())
        identity = [n for n in names if "httpAuthSecurityScheme" in schemes.get(n, {})]
        oauth = [n for n in names if "oauth2SecurityScheme" in schemes.get(n, {})]
        if not identity or not oauth:
            continue
        o2 = schemes[oauth[0]]["oauth2SecurityScheme"]
        flow = (o2.get("flows") or {}).get("deviceCode")
        if not flow or not o2.get("oauth2MetadataUrl"):
            continue
        return DelegationScheme(
            device_authorization_url=flow["deviceAuthorizationUrl"],
            token_url=flow["tokenUrl"],
            metadata_url=o2["oauth2MetadataUrl"],
            scopes=dict(flow.get("scopes") or {}),
        )
    return None


class DeviceCodeClient:
    """OAuth client is the personal agent: client_id is its issuer, authenticated by a fresh JWT per call."""

    def __init__(self, scheme: DelegationScheme, client_id: str, get_token: Callable[[], str],
                 http: Optional[httpx.AsyncClient] = None, now: Callable[[], float] = time.time):
        self.scheme = scheme
        self.client_id = client_id
        self._get_token = get_token
        self._http = http
        self._now = now

    async def _post(self, url: str, params: Dict[str, str]) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._get_token()}", "Accept": "application/json"}
        data = {**params, "client_id": self.client_id}
        if self._http is not None:
            response = await self._http.post(url, data=data, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, data=data, headers=headers)
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code == 200:
            return body
        # A bare 401 is the agent JWT being refused (spec §3.4); anything else is an OAuth error.
        if response.status_code != 401 and isinstance(body, dict) and body.get("error"):
            raise OAuthError(response.status_code, str(body["error"]), str(body.get("error_description", "")))
        raise OAuthError(response.status_code, "http_error", f"HTTP {response.status_code}")

    def _token(self, body: Dict[str, Any]) -> DelegationToken:
        return DelegationToken(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            scopes=[s for s in str(body.get("scope", "")).split(" ") if s],  # what the User approved, maybe less
            expires_at=self._now() + int(body["expires_in"]),
        )

    async def start(self, scopes: List[str]) -> DeviceAuthorization:
        if not scopes:
            raise ValueError("Request at least one scope")
        unknown = [s for s in scopes if s not in self.scheme.scopes]
        if unknown:  # spec §5.2: request only ids that are on the card
            raise ValueError(f"Scopes not on the Agent Card: {', '.join(unknown)}")
        body = await self._post(self.scheme.device_authorization_url, {"scope": " ".join(dict.fromkeys(scopes))})
        return DeviceAuthorization(
            device_code=body["device_code"],
            user_code=body["user_code"],
            verification_uri=body["verification_uri"],
            verification_uri_complete=body["verification_uri_complete"],
            expires_at=self._now() + int(body["expires_in"]),
            interval=int(body.get("interval", 5)),
        )

    async def poll(self, device_code: str) -> Union[str, DelegationToken]:
        """'pending', 'slow_down', or the token. access_denied and expired_token raise OAuthError."""
        try:
            return self._token(await self._post(self.scheme.token_url, {"grant_type": DEVICE_CODE_GRANT, "device_code": device_code}))
        except OAuthError as e:
            if e.error in ("authorization_pending", "slow_down"):
                return "pending" if e.error == "authorization_pending" else "slow_down"
            raise

    async def wait(self, authorization: DeviceAuthorization,
                   sleep: Callable[[float], Awaitable[None]]) -> DelegationToken:
        interval = authorization.interval
        while self._now() + interval <= authorization.expires_at:
            await sleep(interval)
            result = await self.poll(authorization.device_code)
            if isinstance(result, DelegationToken):
                return result
            if result == "slow_down":
                interval += 5  # RFC 8628 §3.5
        raise OAuthError(400, "expired_token", "The device code expired before approval")

    async def refresh(self, refresh_token: str) -> DelegationToken:
        return self._token(await self._post(self.scheme.token_url, {"grant_type": "refresh_token", "refresh_token": refresh_token}))


async def fetch_jwks_for(metadata_url: str, http: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    """RFC 8414 metadata names the keys that sign delegation tokens and receipts (spec §5.1)."""
    async def go(client: httpx.AsyncClient) -> Dict[str, Any]:
        meta = (await client.get(metadata_url, headers={"Accept": "application/json"})).json()
        return (await client.get(meta["jwks_uri"])).json()

    if http is not None:
        return await go(http)
    async with httpx.AsyncClient(timeout=15) as client:
        return await go(client)


def verify_receipt(receipt: Dict[str, Any], jwks: Dict[str, Any], expected: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Spec §5.6: the compact JWS must verify against the Brand's published keys and match the
    plain `claims` it travels with. Returns the signed claims."""
    token = receipt.get("jws")
    if not isinstance(token, str):
        raise ReceiptError("Receipt has no jws")
    try:
        header = jws.get_unverified_header(token)
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")), None)
        if key is None:
            raise ReceiptError(f"No published key for kid {header.get('kid')}")
        payload = json.loads(jws.verify(token, key, algorithms=["ES256", "RS256"]))
    except JWSError as e:
        raise ReceiptError(f"Receipt signature is invalid: {e}") from e
    if payload != receipt.get("claims"):
        raise ReceiptError("Receipt claims do not match the signed payload")
    for name, value in (expected or {}).items():
        if payload.get(name) != value:
            raise ReceiptError(f"Receipt {name} does not match")
    return payload
