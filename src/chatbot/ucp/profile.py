"""Merchant profile parsing and capability negotiation (UCP 2026-08-25).

The merchant publishes its profile at /.well-known/ucp. Shape:

    {"ucp": {"version", "services", "capabilities", "payment_handlers"},
     "keys": [JWK, ...]}

`services`, `capabilities` and `payment_handlers` are objects keyed by
reverse-DNS name, each holding a list of entries.
"""
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urlparse

AGENT_UCP_VERSION = "2026-08-25"
SHOPPING_SERVICE = "dev.ucp.shopping"
CHECKOUT_CAPABILITY = "dev.ucp.shopping.checkout"

# Capabilities this agent implements or intends to. Negotiation intersects
# these with what the merchant advertises.
AGENT_CAPABILITIES: Set[str] = {
    "dev.ucp.shopping.checkout",
    "dev.ucp.shopping.cart",
    "dev.ucp.shopping.order",
    "dev.ucp.shopping.discount",
    "dev.ucp.shopping.fulfillment",
    "dev.ucp.shopping.buyer_consent",
    "dev.ucp.shopping.catalog.search",
    "dev.ucp.shopping.catalog.lookup",
    "dev.ucp.common.identity_linking",
    "dev.ucp.common.loyalty",
    "dev.ucp.common.payment.split_payments",
}

SPLIT_PAYMENTS_CAPABILITY = "dev.ucp.common.payment.split_payments"
LOYALTY_HANDLER_ID = "mock_loyalty_points"

# Cache-Control max-age bounds. The spec requires merchants to serve at least 60s.
MIN_CACHE_SECONDS = 60
MAX_CACHE_SECONDS = 86400
DEFAULT_CACHE_SECONDS = 300


class ProfileError(Exception):
    """The merchant profile is missing, malformed, or unsafe to fetch."""


class VersionUnsupported(ProfileError):
    """No mutually supported protocol version."""


class CapabilitiesIncompatible(ProfileError):
    """The negotiated capability set cannot support the requested operation."""


@dataclass
class MerchantProfile:
    """Parsed merchant profile."""

    version: str
    services: Dict[str, List[Dict[str, Any]]]
    capabilities: Dict[str, List[Dict[str, Any]]]
    payment_handlers: Dict[str, List[Dict[str, Any]]]
    keys: List[Dict[str, Any]] = field(default_factory=list)
    supported_versions: Dict[str, str] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def rest_endpoint(self) -> Optional[str]:
        """REST endpoint of the shopping service, or None if not advertised."""
        for entry in self.services.get(SHOPPING_SERVICE, []):
            if entry.get("transport") == "rest" and entry.get("endpoint"):
                return entry["endpoint"].rstrip("/")
        return None

    def handlers(self) -> List[Dict[str, Any]]:
        """Flat list of payment handler entries (each has an `id`)."""
        return [h for entries in self.payment_handlers.values() for h in entries]

    def handler_by_id(self, handler_id: str) -> Optional[Dict[str, Any]]:
        for handler in self.handlers():
            if handler.get("id") == handler_id:
                return handler
        return None

    def key_by_kid(self, kid: str) -> Optional[Dict[str, Any]]:
        for key in self.keys:
            if key.get("kid") == kid:
                return key
        return None


def parse_profile(doc: Dict[str, Any]) -> MerchantProfile:
    """Parse and minimally validate a /.well-known/ucp document."""
    if not isinstance(doc, dict) or not isinstance(doc.get("ucp"), dict):
        raise ProfileError("Profile has no 'ucp' object")
    ucp = doc["ucp"]

    version = ucp.get("version")
    if not version or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(version)):
        raise ProfileError(f"Profile version missing or not a dated release: {version!r}")

    # The spec requires services and payment_handlers to be present, even if empty.
    for required in ("services", "payment_handlers"):
        if not isinstance(ucp.get(required), dict):
            raise ProfileError(f"Profile is missing required '{required}' object")

    return MerchantProfile(
        version=str(version),
        services=ucp["services"],
        capabilities=ucp.get("capabilities") or {},
        payment_handlers=ucp["payment_handlers"],
        keys=doc.get("keys") or [],
        supported_versions=ucp.get("supported_versions") or {},
        raw=doc,
    )


def _parents(entry: Dict[str, Any]) -> List[str]:
    """`extends` may be a string or a list of strings."""
    extends = entry.get("extends")
    if not extends:
        return []
    return [extends] if isinstance(extends, str) else list(extends)


def negotiate_capabilities(
    profile: MerchantProfile,
    agent_capabilities: Iterable[str] = AGENT_CAPABILITIES,
) -> Set[str]:
    """
    Intersect agent and merchant capabilities, then prune orphaned extensions.

    A single-parent extension is kept only if its parent survives; a
    multi-parent extension needs at least one surviving parent. Pruning
    repeats until stable (overview spec, capability negotiation step 3-4).
    """
    entries: Dict[str, Dict[str, Any]] = {}
    for name, versions in profile.capabilities.items():
        if name not in agent_capabilities or not versions:
            continue
        # Entries are all at the profile's version; take the first.
        entries[name] = versions[0]

    result = set(entries)
    changed = True
    while changed:
        changed = False
        for name in list(result):
            parents = _parents(entries[name])
            if parents and not any(p in result for p in parents):
                result.discard(name)
                changed = True
    return result


def check_version(profile: MerchantProfile, agent_version: str = AGENT_UCP_VERSION) -> None:
    """Raise VersionUnsupported unless the merchant speaks the agent's version."""
    if profile.version == agent_version:
        return
    if agent_version in profile.supported_versions:
        # Version-specific profile exists; this client does not follow it yet.
        raise VersionUnsupported(
            f"Merchant serves {profile.version} at its root profile and lists "
            f"{agent_version} only under supported_versions; fetching "
            f"version-specific profiles is not implemented"
        )
    raise VersionUnsupported(
        f"Merchant version {profile.version} is not supported by this agent ({agent_version})"
    )


def parse_cache_seconds(cache_control: Optional[str]) -> int:
    """Seconds to cache a profile, from Cache-Control max-age, clamped to bounds."""
    if cache_control:
        match = re.search(r"max-age=(\d+)", cache_control, re.IGNORECASE)
        if match:
            return max(MIN_CACHE_SECONDS, min(int(match.group(1)), MAX_CACHE_SECONDS))
    return DEFAULT_CACHE_SECONDS


def is_special_use_address(ip: str) -> bool:
    """True for loopback, private, link-local, reserved and other non-global addresses."""
    try:
        return not ipaddress.ip_address(ip).is_global
    except ValueError:
        return True


def validate_discovery_url(url: str, allow_insecure: bool = False) -> None:
    """
    Reject discovery URLs the spec says a fetcher must not touch: non-HTTPS
    schemes, and hosts resolving to special-use IP addresses (SSRF).

    `allow_insecure` permits http and loopback for local development only.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" and not (allow_insecure and parsed.scheme == "http"):
        raise ProfileError(f"Discovery URL must use HTTPS: {url}")
    if not parsed.hostname:
        raise ProfileError(f"Discovery URL has no host: {url}")
    if allow_insecure:
        return
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ProfileError(f"Cannot resolve discovery host {parsed.hostname}: {e}")
    for info in infos:
        if is_special_use_address(info[4][0]):
            raise ProfileError(
                f"Discovery host {parsed.hostname} resolves to a special-use address"
            )
