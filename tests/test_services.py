"""Tests for service layer."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.chatbot.services.catalog_service import CatalogService, HARDCODED_PRODUCTS
from src.chatbot.services.checkout_service import CheckoutService
from src.chatbot.conversation.state import ConversationState


@pytest.mark.asyncio
async def test_catalog_service_search_fallback():
    """Test catalog service falls back to hardcoded products."""
    mock_ucp_client = MagicMock()
    mock_ucp_client.search_catalog = AsyncMock(return_value=[])

    service = CatalogService(mock_ucp_client)
    results = await service.search_products("roses")

    assert len(results) > 0
    assert any("rose" in r["name"].lower() for r in results)


def test_catalog_service_get_product_by_id():
    """Test getting product by ID."""
    mock_ucp_client = MagicMock()
    service = CatalogService(mock_ucp_client)

    product = service.get_product_by_id("bouquet_roses")
    assert product is not None
    assert product["id"] == "bouquet_roses"

    product = service.get_product_by_id("nonexistent")
    assert product is None


@pytest.mark.asyncio
async def test_checkout_service_start_checkout():
    """Test starting a new checkout."""
    mock_ucp_client = MagicMock()
    mock_ucp_client.create_checkout = AsyncMock(
        return_value={"id": "checkout_123"}
    )

    service = CheckoutService(mock_ucp_client)
    state = ConversationState(user_id="test_user", session_id="test_session")

    line_items = [{"product_id": "test_product", "quantity": 1}]
    response = await service.start_checkout(state, line_items)

    assert response["id"] == "checkout_123"
    assert state.checkout_id == "checkout_123"
    assert state.status == "shopping"
