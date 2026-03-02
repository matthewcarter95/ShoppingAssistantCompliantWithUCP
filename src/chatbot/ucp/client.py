"""UCP API client implementation."""
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from ..config import settings
from ..utils.logger import setup_logger
from .headers import generate_ucp_headers

logger = setup_logger(__name__, settings.log_level)


class UCPClient:
    """Client for interacting with UCP-compliant merchant APIs."""

    def __init__(self, base_url: Optional[str] = None, agent_profile: Optional[str] = None):
        """
        Initialize UCP client.

        Args:
            base_url: Base URL for the UCP merchant API
            agent_profile: UCP agent profile URL
        """
        self.base_url = (base_url or settings.ucp_base_url).rstrip("/")
        self.agent_profile = agent_profile or settings.ucp_agent_profile
        self.client = httpx.AsyncClient(timeout=30.0)
        self._discovery_cache: Optional[Dict[str, Any]] = None
        self._discovery_cache_time: Optional[datetime] = None

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    def _get_headers(self) -> Dict[str, str]:
        """Generate UCP headers for requests."""
        return generate_ucp_headers(self.agent_profile)

    async def discover(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetch UCP discovery document from /.well-known/ucp.

        Caches result for 5 minutes to reduce API calls.

        Args:
            force_refresh: Force a fresh fetch ignoring cache

        Returns:
            Discovery document as dictionary
        """
        # Check cache
        if not force_refresh and self._discovery_cache:
            if self._discovery_cache_time:
                age = datetime.now() - self._discovery_cache_time
                if age < timedelta(minutes=5):
                    logger.debug("Using cached discovery document")
                    return self._discovery_cache

        # Fetch fresh discovery document
        url = f"{self.base_url}/.well-known/ucp"
        headers = self._get_headers()

        try:
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            self._discovery_cache = response.json()
            self._discovery_cache_time = datetime.now()
            logger.info("Fetched UCP discovery document")
            return self._discovery_cache
        except Exception as e:
            logger.error(f"Failed to fetch discovery document: {e}")
            # Return minimal discovery if cache exists
            if self._discovery_cache:
                return self._discovery_cache
            raise

    async def search_catalog(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for products in the catalog.

        Args:
            query: Search query string

        Returns:
            List of product dictionaries
        """
        headers = self._get_headers()

        # Use the UCP products endpoint
        try:
            url = f"{self.base_url}/api/ucp/products"
            logger.info(f"Fetching products from: {url}")
            response = await self.client.get(url, headers=headers)

            logger.info(f"Catalog API response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Catalog API returned data with keys: {list(data.keys())}")

                # Handle UCP API response format
                if isinstance(data, dict) and "products" in data:
                    products = data["products"]
                    logger.info(f"Found {len(products)} products from UCP API")

                    # Filter by query if provided
                    if query:
                        query_lower = query.lower()
                        filtered = [
                            p for p in products
                            if query_lower in p.get("title", "").lower()
                            or query_lower in str(p.get("description", "")).lower()
                        ]
                        if filtered:
                            logger.info(f"Filtered to {len(filtered)} products matching '{query}'")
                            return filtered
                        else:
                            logger.info(f"No matches for '{query}', returning all products")

                    return products
                elif isinstance(data, list):
                    return data

        except Exception as e:
            logger.error(f"UCP catalog search failed: {e}", exc_info=True)

        logger.warning("No catalog API available, returning empty list")
        return []

    async def create_checkout(
        self, line_items: List[Dict[str, Any]], buyer: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new checkout session.

        Args:
            line_items: List of line items with product_id and quantity
            buyer: Optional buyer information

        Returns:
            Checkout session response
        """
        url = f"{self.base_url}/checkout-sessions"
        headers = self._get_headers()

        payload: Dict[str, Any] = {"line_items": line_items}
        if buyer:
            payload["buyer"] = buyer

        logger.info(f"Creating checkout session with {len(line_items)} items")
        response = await self.client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    async def create_checkout_with_payload(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new checkout session with full payload control.

        Args:
            payload: Complete checkout creation payload

        Returns:
            Checkout session response
        """
        url = f"{self.base_url}/checkout-sessions"
        headers = self._get_headers()

        logger.info(f"Creating checkout session with payload")
        response = await self.client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    async def update_checkout(
        self, checkout_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an existing checkout session.

        Args:
            checkout_id: The checkout session ID
            updates: Dictionary of updates to apply

        Returns:
            Updated checkout session response
        """
        url = f"{self.base_url}/checkout-sessions/{checkout_id}"
        headers = self._get_headers()

        logger.info(f"Updating checkout session {checkout_id}")
        response = await self.client.put(url, headers=headers, json=updates)

        # Log detailed error if validation fails
        if response.status_code == 422:
            try:
                error_detail = response.json()
                logger.error(f"422 Validation error: {error_detail}")
            except:
                logger.error(f"422 error body: {response.text}")

        response.raise_for_status()
        return response.json()

    async def complete_checkout(
        self, checkout_id: str, payment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Complete a checkout session with payment.

        Args:
            checkout_id: The checkout session ID
            payment_data: Payment instrument data

        Returns:
            Order completion response
        """
        url = f"{self.base_url}/checkout-sessions/{checkout_id}/complete"
        headers = self._get_headers()

        logger.info(f"Completing checkout session {checkout_id}")
        response = await self.client.post(url, headers=headers, json=payment_data)

        # Log detailed error if validation fails
        if response.status_code == 422:
            try:
                error_detail = response.json()
                logger.error(f"422 Validation error on complete: {error_detail}")
            except:
                logger.error(f"422 error body on complete: {response.text}")

        response.raise_for_status()
        return response.json()

    async def get_checkout(self, checkout_id: str) -> Dict[str, Any]:
        """
        Retrieve a checkout session.

        Args:
            checkout_id: The checkout session ID

        Returns:
            Checkout session data
        """
        url = f"{self.base_url}/checkout-sessions/{checkout_id}"
        headers = self._get_headers()

        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
