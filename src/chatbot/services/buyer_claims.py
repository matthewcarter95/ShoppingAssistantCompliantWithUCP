"""Buyer details carried as custom claims on the merchant access token.

The merchant's Auth0 tenant puts the buyer's name, email and shipping address
on the access token under a claim namespace. The assistant uses them to
pre-fill checkout, but only after the shopper confirms them.

The token is NOT signature-verified here. It arrives straight from the Auth0
token endpoint over TLS, and the values are only ever shown to the shopper for
confirmation. They must never be used to decide access: the merchant verifies
the token itself.
"""
import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class BuyerProfile:
    """Checkout details taken from the merchant token."""

    name: str
    email: str
    # UCP flat postal address: street_address, address_locality,
    # address_region, postal_code, address_country
    address: Dict[str, str]
    address_label: Optional[str] = None

    def address_line(self) -> str:
        """One-line form for showing the shopper."""
        a = self.address
        place = " ".join(p for p in (a.get("address_region"), a.get("postal_code")) if p)
        parts = [a.get("street_address"), a.get("address_locality"), place]
        return ", ".join(p for p in parts if p)

    def summary(self) -> str:
        label = f" ({self.address_label})" if self.address_label else ""
        return (
            f"Name: {self.name}\n"
            f"Email: {self.email}\n"
            f"Ship to{label}: {self.address_line()}"
        )

    def as_buyer_info(self) -> Dict[str, str]:
        """Same keys the typed-details path uses."""
        return {
            "buyer_name": self.name,
            "buyer_email": self.email,
            "shipping_address": self.address_line(),
        }


def unverified_claims(token: Optional[str]) -> Dict[str, Any]:
    """Decode a JWT payload without verifying it. Returns {} if unreadable."""
    if not token or token.count(".") != 2:
        return {}
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _address_from_claim(raw: Any) -> Optional[tuple]:
    """
    Map the claim's address object to a UCP flat address.

    Claim shape: {id, label, street, city, state, zip, country}. A list of
    such objects is accepted too (first one is used; its label is shown so
    the shopper can tell it apart and correct it).
    """
    if isinstance(raw, list):
        raw = next((a for a in raw if isinstance(a, dict)), None)
    if not isinstance(raw, dict):
        return None
    mapped = {
        "street_address": raw.get("street"),
        "address_locality": raw.get("city"),
        "address_region": raw.get("state"),
        "postal_code": raw.get("zip"),
        "address_country": raw.get("country"),
    }
    address = {k: str(v).strip() for k, v in mapped.items() if v not in (None, "")}
    # Without a street, city and postal code the merchant cannot quote shipping
    if not all(address.get(k) for k in ("street_address", "address_locality", "postal_code")):
        return None
    return address, raw.get("label")


def buyer_profile_from_token(
    token: Optional[str],
    namespace: str,
    name_claim: str = "name",
    email_claim: str = "email",
    address_claim: str = "shippingAddress",
) -> Optional[BuyerProfile]:
    """
    Read the buyer's checkout details from the token's custom claims.

    Returns None unless name, email and a usable address are all present, so
    callers can fall back to asking the shopper.
    """
    claims = unverified_claims(token)
    if not claims:
        return None
    base = namespace.rstrip("/")
    name = claims.get(f"{base}/{name_claim}")
    email = claims.get(f"{base}/{email_claim}")
    mapped = _address_from_claim(claims.get(f"{base}/{address_claim}"))
    if not (isinstance(name, str) and name.strip() and isinstance(email, str) and email.strip() and mapped):
        return None
    address, label = mapped
    return BuyerProfile(
        name=name.strip(), email=email.strip(), address=address, address_label=label
    )
