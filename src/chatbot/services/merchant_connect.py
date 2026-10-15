"""When to invite the shopper to connect their merchant account.

The invitation is shown once per session, right after the first product list,
so the shopper can link their account before they start a cart.
"""
from typing import Any, Callable, Dict, Optional

CONNECT_PROMPT = (
    "Connect to the merchant so I can see your loyalty points and apply them at checkout. "
    "You'll sign in with the merchant; I'm only given access to manage your cart and "
    "complete orders you confirm."
)


def merchant_token_usable(
    merchant_auth: Optional[Dict[str, Any]],
    is_expired: Callable[[str], bool],
) -> bool:
    """
    True if the session holds a merchant token that is still good.

    An expired token with no refresh token counts as unusable, because the
    shopper has to sign in again anyway.
    """
    if not merchant_auth or not merchant_auth.get("access_token"):
        return False
    expires_at = merchant_auth.get("expires_at")
    if expires_at and is_expired(expires_at) and not merchant_auth.get("refresh_token"):
        return False
    return True


def should_offer_connect(
    *,
    signed_in: bool,
    found_products: bool,
    token_usable: bool,
    already_offered: bool,
) -> bool:
    """Offer once, to a signed-in shopper without a usable merchant token, after products are shown."""
    return signed_in and found_products and not token_usable and not already_offered
