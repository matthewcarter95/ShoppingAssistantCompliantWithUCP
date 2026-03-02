#!/bin/bash
# Local testing script for the shopping assistant chatbot

set -e

echo "=== Shopping Assistant Chatbot - Local Testing ==="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found. Copy .env.example and configure it first."
    exit 1
fi

# Check for OPENAI_API_KEY
if ! grep -q "OPENAI_API_KEY=sk-" .env 2>/dev/null; then
    echo "Warning: OPENAI_API_KEY not properly set in .env"
    echo "Please add your OpenAI API key to .env"
fi

BASE_URL="http://localhost:8000"
SESSION_ID=$(uuidgen)

echo "Using session ID: $SESSION_ID"
echo ""

# Test 1: Health check
echo "Test 1: Health Check"
curl -s "$BASE_URL/health" | jq .
echo ""

# Test 2: Discovery
echo "Test 2: UCP Discovery"
curl -s "$BASE_URL/discovery" | jq .
echo ""

# Test 3: Create session
echo "Test 3: Create Session"
curl -s -X POST "$BASE_URL/session/new" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user"}' | jq .
echo ""

# Test 4: Search products
echo "Test 4: Search Products (roses)"
curl -s -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"user_id\": \"test_user\", \"message\": \"Show me roses\"}" | jq .
echo ""

# Test 5: Add to cart
echo "Test 5: Add to Cart"
curl -s -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"user_id\": \"test_user\", \"message\": \"Add the red rose bouquet to my cart\"}" | jq .
echo ""

# Test 6: Apply discount
echo "Test 6: Apply Discount Code"
curl -s -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"user_id\": \"test_user\", \"message\": \"Apply code 10OFF\"}" | jq .
echo ""

# Test 7: Complete order
echo "Test 7: Complete Order"
curl -s -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"user_id\": \"test_user\", \"message\": \"Complete my order. John Doe, john@example.com, 123 Main St, Anytown CA 12345\"}" | jq .
echo ""

echo "=== Testing Complete ==="
