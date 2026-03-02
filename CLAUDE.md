# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ShoppingAssistantCompliantWithUCP** - A conversational shopping assistant chatbot that integrates with UCP (Universal Commerce Protocol) services, uses OpenAI for natural language understanding, and deploys to AWS as a serverless application.

## Architecture

### High-Level Architecture
```
[S3 Static Website] → [Lambda Function URL] → [FastAPI + Mangum]
                                                      ↓
                                    ┌─────────────────┴─────────────────┐
                                    ↓                 ↓                  ↓
                              [OpenAI API]    [UCP Merchant API]  [DynamoDB]
```

### Components

1. **Frontend** (`frontend/`)
   - Static HTML/CSS/JS chat interface
   - Hosted on S3 with static website hosting
   - Communicates with Lambda via Function URL

2. **Backend** (`src/chatbot/`)
   - FastAPI application wrapped with Mangum for Lambda
   - OpenAI NLU with function calling for intent recognition
   - UCP client for checkout operations
   - DynamoDB for session persistence

3. **Services**
   - `CatalogService`: Product search (UCP catalog API + hardcoded fallback)
   - `CheckoutService`: Checkout workflow orchestration
   - `PaymentService`: Payment completion with mock handler

## Development Workflow

### Local Development

```bash
# Install dependencies
make dev

# Set up environment
cp .env.example .env
# Edit .env and add OPENAI_API_KEY

# Run locally
make local

# Access at http://localhost:8000
# Open frontend/index.html in browser
```

### Testing

```bash
# Run tests
make test

# Lint code
make lint

# Format code
make format
```

### Deployment

```bash
# Build SAM application
make build

# Deploy to AWS
make deploy

# Deploy frontend to S3
make deploy-frontend FRONTEND_BUCKET=your-bucket-name
```

## Key Files

- `src/chatbot/app.py` - FastAPI routes and main chat logic
- `src/chatbot/main.py` - Lambda handler (Mangum wrapper)
- `src/chatbot/ucp/client.py` - UCP API client
- `src/chatbot/nlu/openai_client.py` - OpenAI integration
- `src/chatbot/nlu/tools.py` - Function calling tool definitions
- `src/chatbot/services/` - Business logic services
- `src/chatbot/conversation/manager.py` - DynamoDB session management
- `template.yaml` - AWS SAM infrastructure definition

## UCP Happy Path Implementation

The chatbot implements the standard UCP checkout flow:

1. **Product Search** - Query catalog API or use hardcoded fallback
2. **Create Checkout** - POST /checkout-sessions with line items
3. **Update Cart** - PUT /checkout-sessions/{id} with updated items
4. **Apply Discounts** - PUT /checkout-sessions/{id} with discount codes
5. **Setup Fulfillment** - PUT /checkout-sessions/{id} with destinations and methods
6. **Select Shipping** - PUT /checkout-sessions/{id} with fulfillment selection
7. **Complete Order** - POST /checkout-sessions/{id}/complete with payment

All UCP requests include required headers: UCP-Agent, request-signature, idempotency-key, request-id.

## Important Notes

- Uses OpenAI function calling to extract user intents
- Falls back to hardcoded products if UCP catalog API unavailable
- Mock payment handler only (success_token for testing)
- Sessions auto-expire after 30 days (DynamoDB TTL)
- No user authentication in MVP (public Lambda URL)
- Auto-selects first available shipping option
