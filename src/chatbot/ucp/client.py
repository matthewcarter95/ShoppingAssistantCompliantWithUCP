"""UCP API client implementation (UCP 2026-08-25, REST binding)."""
import asyncio
import time
from typing import Any, Dict, List, Optional, Set

import httpx

from ..config import settings
from ..utils.logger import setup_logger
from .headers import generate_ucp_headers
from .profile import (
    AGENT_UCP_VERSION,
    CHECKOUT_CAPABILITY,
    MerchantProfile,
    ProfileError,
    check_version,
    negotiate_capabilities,
    parse_cache_seconds,
    parse_profile,
    validate_discovery_url,
)

logger = setup_logger(__name__, settings.log_level)


class UCPError(Exception):
    """A merchant call failed. Carries the merchant's `messages` when present."""

    def __init__(
        self,
        status_code: int,
        messages: Optional[List[Dict[str, Any]]] = None,
        body: Optional[str] = None,
        continue_url: Optional[str] = None,
    ):
        self.status_code = status_code
        self.messages = messages or []
        self.body = body
        self.continue_url = continue_url
        super().__init__(self._describe())

    def _describe(self) -> str:
        if self.messages:
            text = "; ".join(
                f"{m.get('code', m.get('type', 'error'))}: {m.get('content', '')}"
                for m in self.messages
            )
            return f"Merchant returned {self.status_code}: {text}"
        return f"Merchant returned {self.status_code}: {(self.body or '')[:200]}"

    @property
    def codes(self) -> Set[str]:
        return {str(m.get("code")) for m in self.messages if m.get("code")}


class UCPClient:
    """Client for interacting with UCP-compliant merchant APIs."""

    def __init__(self, base_url: Optional[str] = None, agent_profile: Optional[str] = None):
        """
        Initialize UCP client.

        Args:
            base_url: Origin of the merchant, used only to find /.well-known/ucp.
                The REST endpoint comes from the merchant's profile.
            agent_profile: URL of this agent's profile (sent in UCP-Agent)
        """
        self.base_url = (base_url or settings.ucp_base_url).rstrip("/")
        self.agent_profile = agent_profile or settings.ucp_agent_profile
        self.client = httpx.AsyncClient(timeout=30.0)
        self._profile: Optional[MerchantProfile] = None
        self._profile_expires: float = 0.0
        self._capabilities: Set[str] = set()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    # ------------------------------------------------------------------
    # Discovery and negotiation
    # ------------------------------------------------------------------

    async def get_profile(self, force_refresh: bool = False) -> MerchantProfile:
        """
        Fetch, validate and negotiate the merchant profile.

        Cached for the merchant's Cache-Control max-age (clamped to 60s-24h).
        If a refresh fails, the previous profile is served rather than failing.

        Raises:
            ProfileError: no usable profile and nothing cached
            VersionUnsupported: merchant does not speak this agent's version
            CapabilitiesIncompatible: merchant lacks checkout after negotiation
        """
        if not force_refresh and self._profile and time.monotonic() < self._profile_expires:
            return self._profile

        url = f"{self.base_url}/.well-known/ucp"
        try:
            await asyncio.to_thread(
                validate_discovery_url, url, settings.ucp_allow_insecure
            )
            response = await self.client.get(
                url, headers={"Accept": "application/json"}, follow_redirects=False
            )
            if response.is_redirect:
                raise ProfileError(f"Discovery must not redirect (got {response.status_code})")
            response.raise_for_status()
            profile = parse_profile(response.json())
            check_version(profile)

            endpoint = profile.rest_endpoint()
            if not endpoint:
                raise ProfileError("Profile advertises no REST endpoint for dev.ucp.shopping")
            await asyncio.to_thread(
                validate_discovery_url, endpoint, settings.ucp_allow_insecure
            )

            capabilities = negotiate_capabilities(profile)
            if CHECKOUT_CAPABILITY not in capabilities:
                from .profile import CapabilitiesIncompatible

                raise CapabilitiesIncompatible(
                    f"No compatible checkout capability (negotiated: {sorted(capabilities)})"
                )
        except Exception as e:
            logger.error(f"Failed to fetch merchant profile: {e}")
            if self._profile:
                logger.warning("Serving previously fetched merchant profile")
                return self._profile
            raise

        self._profile = profile
        self._capabilities = capabilities
        self._profile_expires = time.monotonic() + parse_cache_seconds(
            response.headers.get("cache-control")
        )
        logger.info(
            f"Merchant profile {profile.version}, endpoint {endpoint}, "
            f"negotiated {len(capabilities)} capabilities"
        )
        return profile

    async def discover(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Return the raw merchant discovery document."""
        return (await self.get_profile(force_refresh)).raw

    async def has_capability(self, name: str) -> bool:
        """True if `name` survived negotiation with the merchant."""
        await self.get_profile()
        return name in self._capabilities

    async def _endpoint(self) -> str:
        endpoint = (await self.get_profile()).rest_endpoint()
        assert endpoint  # guaranteed by get_profile
        return endpoint

    # ------------------------------------------------------------------
    # Request plumbing
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        merchant_token: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a UCP REST request and return the parsed JSON body.

        POST/PUT get an Idempotency-Key; every call gets UCP-Agent and Request-Id.

        Raises:
            UCPError: non-2xx, non-JSON, or a 2xx carrying `ucp.status == "error"`
                (spec: capabilities_incompatible and all-items-unavailable).
        """
        url = f"{await self._endpoint()}{path}"
        headers = generate_ucp_headers(
            self.agent_profile,
            idempotent=method in ("POST", "PUT"),
            idempotency_key=idempotency_key,
            has_body=json is not None,
        )
        if merchant_token:
            headers["Authorization"] = f"Bearer {merchant_token}"

        response = await self.client.request(method, url, headers=headers, json=json)

        try:
            body = response.json()
        except ValueError:
            body = None

        if response.status_code >= 400 or body is None:
            logger.error(f"{method} {path} -> {response.status_code}: {response.text[:300]}")
            messages = body.get("messages") if isinstance(body, dict) else None
            if isinstance(body, dict) and not messages and body.get("code"):
                # Top-level protocol error, e.g. version_unsupported (422)
                messages = [{"code": body["code"], "content": body.get("content", "")}]
            raise UCPError(
                response.status_code,
                messages,
                body=response.text,
                continue_url=body.get("continue_url") if isinstance(body, dict) else None,
            )

        if isinstance(body.get("ucp"), dict) and body["ucp"].get("status") == "error":
            raise UCPError(
                response.status_code, body.get("messages"), continue_url=body.get("continue_url")
            )
        return body

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    async def search_catalog(
        self, query: str, merchant_token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search the catalog (POST /catalog/search).

        The merchant requires a query or a filter; an empty query is rejected
        rather than treated as "list everything".

        Returns:
            Product dicts in the spec's catalog shape (may be empty)
        """
        if not query or not query.strip():
            raise ValueError("Catalog search requires a non-empty query")
        body = await self._request(
            "POST", "/catalog/search", json={"query": query}, merchant_token=merchant_token
        )
        return body.get("products", [])

    async def lookup_products(
        self, ids: List[str], merchant_token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Look up products by id (POST /catalog/lookup).

        Unknown ids are reported by the merchant as `not_found` info messages
        and are simply absent from the result.
        """
        body = await self._request(
            "POST", "/catalog/lookup", json={"ids": ids}, merchant_token=merchant_token
        )
        return body.get("products", [])

    # ------------------------------------------------------------------
    # Checkout
    # ------------------------------------------------------------------

    async def create_checkout_with_payload(
        self, payload: Dict[str, Any], merchant_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new checkout session with full payload control.

        Args:
            payload: Complete checkout creation payload
            merchant_token: Optional merchant access token for authorization

        Returns:
            Checkout session response
        """
        logger.info("Creating checkout session")
        return await self._request(
            "POST", "/checkout-sessions", json=payload, merchant_token=merchant_token
        )

    async def update_checkout(
        self, checkout_id: str, updates: Dict[str, Any], merchant_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update an existing checkout session (full replacement).

        Args:
            checkout_id: The checkout session ID
            updates: Complete checkout body to apply
            merchant_token: Optional merchant access token for authorization

        Returns:
            Updated checkout session response
        """
        logger.info(f"Updating checkout session {checkout_id}")
        return await self._request(
            "PUT", f"/checkout-sessions/{checkout_id}", json=updates, merchant_token=merchant_token
        )

    async def complete_checkout(
        self, checkout_id: str, payment_data: Dict[str, Any], merchant_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete a checkout session with payment.

        Args:
            checkout_id: The checkout session ID
            payment_data: Complete request body
            merchant_token: Optional merchant access token for authorization

        Returns:
            Checkout response (with `order` when completed)
        """
        logger.info(f"Completing checkout session {checkout_id}")
        return await self._request(
            "POST",
            f"/checkout-sessions/{checkout_id}/complete",
            json=payment_data,
            merchant_token=merchant_token,
        )

    async def get_checkout(
        self, checkout_id: str, merchant_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve a checkout session.

        Args:
            checkout_id: The checkout session ID
            merchant_token: Optional merchant access token for authorization

        Returns:
            Checkout session data
        """
        return await self._request(
            "GET", f"/checkout-sessions/{checkout_id}", merchant_token=merchant_token
        )
