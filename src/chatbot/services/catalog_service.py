"""Product catalog service."""
from typing import List, Dict, Any, Optional

from ..ucp.client import UCPClient
from ..utils.logger import setup_logger
from ..config import settings

logger = setup_logger(__name__, settings.log_level)

# Hardcoded fallback products (matching real UCP API)
HARDCODED_PRODUCTS = [
    {
        "id": "bouquet_roses",
        "name": "Bouquet of Red Roses",
        "description": "Beautiful Bouquet of Red Roses",
        "price": 35.0,
        "currency": "USD",
        "image_url": "https://example.com/roses.jpg",
    },
    {
        "id": "pot_ceramic",
        "name": "Ceramic Pot",
        "description": "Ceramic pot for indoor plants",
        "price": 15.0,
        "currency": "USD",
        "image_url": "https://example.com/pot.jpg",
    },
    {
        "id": "bouquet_tulips",
        "name": "Bouquet of Tulips",
        "description": "Beautiful Bouquet of Tulips",
        "price": 25.0,
        "currency": "USD",
        "image_url": "https://example.com/tulips.jpg",
    },
    {
        "id": "bouquet_mixed",
        "name": "Mixed Flower Bouquet",
        "description": "Beautiful Mixed Flower Bouquet",
        "price": 40.0,
        "currency": "USD",
        "image_url": "https://example.com/mixed.jpg",
    },
    {
        "id": "bouquet_sunflowers",
        "name": "Sunflower Bundle",
        "description": "Bright sunflower bundle",
        "price": 25.0,
        "currency": "USD",
        "image_url": "https://example.com/sunflowers.jpg",
    },
    {
        "id": "orchid_white",
        "name": "White Orchid",
        "description": "Elegant white orchid plant",
        "price": 45.0,
        "currency": "USD",
        "image_url": "https://example.com/orchid.jpg",
    },
]


class CatalogService:
    """Service for searching and retrieving product information."""

    def __init__(self, ucp_client: UCPClient):
        """
        Initialize catalog service.

        Args:
            ucp_client: UCP client instance
        """
        self.ucp_client = ucp_client

    async def search_products(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for products matching the query.

        First attempts to query UCP catalog API, falls back to hardcoded products.

        Args:
            query: Search query string

        Returns:
            List of product dictionaries (normalized format)
        """
        try:
            # Attempt UCP catalog search
            results = await self.ucp_client.search_catalog(query)
            if results:
                logger.info(f"Found {len(results)} products via UCP catalog API")
                # Normalize UCP API format to our format
                return self._normalize_products(results)
        except Exception as e:
            logger.warning(f"UCP catalog search failed: {e}")

        # Fallback to hardcoded products
        logger.info("Using hardcoded product catalog")
        return self._search_hardcoded(query)

    def _normalize_products(self, ucp_products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize UCP API product format to our internal format.

        UCP 2026-08-25 format: {id, title, description: {plain}, price_range,
        variants: [{id, price: {amount, currency}, availability: {available}}],
        media: [{url}], url}. Amounts are in minor units.
        Our format: {id, name, description, price (major units), price_minor,
        currency, image_url, link}. `id` is the first purchasable variant's id,
        because that is the `item.id` checkout expects.

        Args:
            ucp_products: Products from UCP API

        Returns:
            Normalized product list
        """
        normalized = []
        for product in ucp_products:
            variants = product.get("variants") or []
            # Prefer the first variant that is available for purchase
            variant = next(
                (v for v in variants if (v.get("availability") or {}).get("available", True)),
                None,
            )
            if variant is None:
                continue  # every variant unavailable (or no variants)

            price = variant.get("price") or {}
            amount = price.get("amount", 0)
            description = product.get("description") or {}
            media = product.get("media") or []

            normalized.append({
                "id": variant["id"],
                "name": product.get("title", variant["id"]),
                "description": description.get("plain", "") if isinstance(description, dict) else str(description),
                "price_minor": amount,
                # Display price assumes a 2-decimal currency; exact handling is
                # a Step 7 (frontend) concern.
                "price": amount / 100,
                "currency": price.get("currency", "USD"),
                "image_url": media[0].get("url", "") if media else "",
                "link": product.get("url", ""),
            })

        return normalized

    def _search_hardcoded(self, query: str) -> List[Dict[str, Any]]:
        """
        Search hardcoded products by query.

        Args:
            query: Search query string

        Returns:
            List of matching products
        """
        query_lower = query.lower()
        results = []

        for product in HARDCODED_PRODUCTS:
            # Simple keyword matching
            if (
                query_lower in product["name"].lower()
                or query_lower in product["description"].lower()
            ):
                results.append(product)

        # If no matches, return all products
        if not results:
            logger.debug("No specific matches, returning all products")
            return HARDCODED_PRODUCTS

        return results

    async def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a product by its ID.

        Tries UCP API first, falls back to hardcoded products.

        Args:
            product_id: Product identifier

        Returns:
            Product dictionary if found, None otherwise
        """
        try:
            found = await self.ucp_client.lookup_products([product_id])
            for product in self._normalize_products(found):
                if product["id"] == product_id:
                    return product
        except Exception as e:
            logger.debug(f"Failed to get product from UCP API: {e}")

        # Fallback to hardcoded
        for product in HARDCODED_PRODUCTS:
            if product["id"] == product_id:
                return product
        return None
