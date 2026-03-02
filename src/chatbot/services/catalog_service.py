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

        UCP format: {id, title, description, price: {value, currency}, ...}
        Our format: {id, name, description, price, currency, ...}

        Args:
            ucp_products: Products from UCP API

        Returns:
            Normalized product list
        """
        normalized = []
        for product in ucp_products:
            # Skip out of stock items
            if product.get("availability") == "out_of_stock":
                continue

            normalized_product = {
                "id": product.get("id"),
                "name": product.get("title", product.get("id")),
                "description": product.get("description", ""),
                "price": product.get("price", {}).get("value", 0),
                "currency": product.get("price", {}).get("currency", "USD"),
                "image_url": product.get("image_link", ""),
                "link": product.get("link", ""),
            }
            normalized.append(normalized_product)

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
            # Try to get from UCP API
            all_products = await self.ucp_client.search_catalog("")
            if all_products:
                # Normalize and find by ID
                normalized = self._normalize_products(all_products)
                for product in normalized:
                    if product["id"] == product_id:
                        return product
        except Exception as e:
            logger.debug(f"Failed to get product from UCP API: {e}")

        # Fallback to hardcoded
        for product in HARDCODED_PRODUCTS:
            if product["id"] == product_id:
                return product
        return None
