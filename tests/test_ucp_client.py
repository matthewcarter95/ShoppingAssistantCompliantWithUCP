"""Tests for UCP client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.chatbot.ucp.client import UCPClient
from src.chatbot.ucp.headers import generate_ucp_headers


def test_generate_ucp_headers():
    """Test UCP header generation."""
    headers = generate_ucp_headers("https://agent.example/profile")

    assert "UCP-Agent" in headers
    assert "request-signature" in headers
    assert "idempotency-key" in headers
    assert "request-id" in headers
    assert headers["UCP-Agent"] == 'profile="https://agent.example/profile"'


@pytest.mark.asyncio
async def test_ucp_client_discover():
    """Test UCP discovery endpoint."""
    client = UCPClient()

    with patch.object(client.client, "get", new=AsyncMock()) as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": "1.0"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = await client.discover()

        assert result == {"version": "1.0"}
        mock_get.assert_called_once()

    await client.close()


@pytest.mark.asyncio
async def test_ucp_client_create_checkout():
    """Test creating a checkout session."""
    client = UCPClient()

    line_items = [{"product_id": "test_product", "quantity": 1}]

    with patch.object(client.client, "post", new=AsyncMock()) as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "checkout_123"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = await client.create_checkout(line_items)

        assert result == {"id": "checkout_123"}
        mock_post.assert_called_once()

    await client.close()
