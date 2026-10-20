"""PACT Identity client (spec §2–4, §6): fetch a Brand's Agent Card and exchange messages."""
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union

import httpx

A2A_VERSION = "1.0"


class PactError(Exception):
    """A2A error envelope (spec §6). The reason is error.details[0].reason, never inferred from status."""

    def __init__(self, http_status: int, reason: str, message: str):
        super().__init__(f"{reason or http_status}: {message}")
        self.http_status = http_status
        self.reason = reason
        self.message = message


class PactHttpError(Exception):
    """Plain HTTP failure with no A2A body: 401, 404, 405, 429."""

    def __init__(self, http_status: int, retry_after: Optional[float] = None, www_authenticate: str = ""):
        super().__init__(f"HTTP {http_status}")
        self.http_status = http_status
        self.retry_after = retry_after
        self.www_authenticate = www_authenticate

    @property
    def token_rejected(self) -> bool:
        """401 with error="invalid_token": the delegation token (not the agent JWT) was refused."""
        return self.http_status == 401 and 'error="invalid_token"' in self.www_authenticate


DELEGATION_HEADER = "X-A2A-User-Delegation"
RECEIPT_KEY = "pact.receipt"
MISSING_SCOPES_KEY = "pact.missingScopes"
VERIFICATION_URI_KEY = "pact.verificationUriComplete"


@dataclass(frozen=True)
class PactReply:
    text: str
    context_id: str
    message: Dict[str, Any]
    receipt: Optional[Dict[str, Any]] = None  # {"jws", "claims"}; present on delegated replies (spec §5.6)


@dataclass(frozen=True)
class AuthRequired:
    """Spec §5.5 step-up: the Brand needs scopes the token lacks. The conversation stays open."""

    context_id: str
    text: str
    missing_scopes: List[str]
    verification_uri_complete: Optional[str]


def interface_url(card: Dict[str, Any]) -> str:
    """The interface is picked by binding and version, never by position (spec §2.1)."""
    for candidate in card.get("supportedInterfaces", []):
        if candidate.get("protocolBinding") == "HTTP+JSON" and candidate.get("protocolVersion") == A2A_VERSION:
            return str(candidate["url"]).rstrip("/")
    raise ValueError("Agent Card has no HTTP+JSON 1.0 interface")


def reply_text(message: Dict[str, Any]) -> str:
    return "\n".join(p["text"] for p in message.get("parts", []) if isinstance(p, dict) and isinstance(p.get("text"), str))


async def fetch_agent_card(card_url: str, http: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    """No authentication. An unknown Brand is a bare 404."""
    async def go(client: httpx.AsyncClient) -> Dict[str, Any]:
        response = await client.get(card_url, follow_redirects=True)
        if response.status_code != 200:
            raise PactHttpError(response.status_code)
        return response.json()

    if http is not None:
        return await go(http)
    async with httpx.AsyncClient(timeout=10) as client:
        return await go(client)


class PactClient:
    """Sends messages to one Brand. `get_token` returns a fresh personal-agent JWT per request."""

    def __init__(self, url: str, get_token: Callable[[], str], http: Optional[httpx.AsyncClient] = None):
        self.url = url.rstrip("/")
        self._get_token = get_token
        self._http = http

    async def send_message(self, text: str, context_id: Optional[str] = None,
                           message_id: Optional[str] = None) -> PactReply:
        """Identity-profile send. A step-up task is an error here; use send_delegated for that."""
        result = await self.send_delegated(text, context_id=context_id, message_id=message_id)
        if isinstance(result, AuthRequired):
            raise PactError(200, "UNSUPPORTED_RESPONSE", "Expected a message reply with a contextId")
        return result

    async def send_delegated(self, text: str, context_id: Optional[str] = None, message_id: Optional[str] = None,
                             delegation_token: Optional[str] = None) -> Union[PactReply, AuthRequired]:
        """`message_id` is generated unless given; resending the same one is a safe retry (spec §4.3).
        With a delegation token the Brand acts as the User within its scopes (spec §5.5)."""
        if not text.strip():
            raise ValueError("Message text must not be blank")
        message: Dict[str, Any] = {
            "messageId": message_id or str(uuid.uuid4()),
            "role": "ROLE_USER",
            "parts": [{"text": text, "mediaType": "text/plain"}],
        }
        if context_id:
            message["contextId"] = context_id
        headers = {
            "A2A-Version": A2A_VERSION,
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }
        if delegation_token:
            headers[DELEGATION_HEADER] = f"Bearer {delegation_token}"
        body = {"message": message}

        if self._http is not None:
            response = await self._http.post(f"{self.url}/message:send", json=body, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{self.url}/message:send", json=body, headers=headers)
        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> Union[PactReply, AuthRequired]:
        if response.status_code != 200:
            envelope: Dict[str, Any] = {}
            try:
                envelope = response.json().get("error") or {}
            except Exception:
                pass
            if envelope:
                details: List[Dict[str, Any]] = envelope.get("details") or [{}]
                raise PactError(response.status_code, str(details[0].get("reason", "")), str(envelope.get("message", "")))
            retry = response.headers.get("Retry-After")
            raise PactHttpError(
                response.status_code,
                float(retry) if retry and retry.replace(".", "", 1).isdigit() else None,
                www_authenticate=_www_authenticate(response),
            )
        data = response.json()
        task = data.get("task")
        if isinstance(task, dict):
            state = (task.get("status") or {}).get("state")
            if state != "TASK_STATE_AUTH_REQUIRED":
                raise PactError(200, "UNSUPPORTED_RESPONSE", f"Unexpected task state {state}")
            meta = task.get("metadata") or {}
            status_message = (task.get("status") or {}).get("message") or {}
            return AuthRequired(
                context_id=str(task.get("contextId", "")),
                text=reply_text(status_message),
                missing_scopes=list(meta.get(MISSING_SCOPES_KEY) or []),
                verification_uri_complete=meta.get(VERIFICATION_URI_KEY),
            )
        message = data.get("message")
        if not isinstance(message, dict) or not message.get("contextId"):
            raise PactError(200, "UNSUPPORTED_RESPONSE", "Expected a message reply with a contextId")
        return PactReply(text=reply_text(message), context_id=message["contextId"], message=message,
                         receipt=(message.get("metadata") or {}).get(RECEIPT_KEY))


def _www_authenticate(response: httpx.Response) -> str:
    """Lambda Function URLs rename this header to x-amzn-remapped-www-authenticate. Accept either."""
    return response.headers.get("www-authenticate") or response.headers.get("x-amzn-remapped-www-authenticate") or ""
