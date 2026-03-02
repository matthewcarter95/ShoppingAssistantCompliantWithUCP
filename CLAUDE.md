# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ShoppingAssistantCompliantWithUCP** - A conversational shopping assistant chatbot that integrates with UCP (Universal Commerce Protocol) services, uses OpenAI for natural language understanding, and deploys to AWS as a serverless application.

## Architecture

### High-Level Architecture
```
[Amplify Static Website] → [Lambda Function URL] → [FastAPI + Mangum]
           ↓                                                  ↓
    [Shopping Auth0]                       ┌─────────────────┴─────────────────┐
           ↓                              ↓                 ↓                  ↓
    [Merchant Auth0] ←─────────→   [OpenAI API]    [UCP Merchant API]  [DynamoDB]
```

### Request Flow

1. **User logs in** → Auth0 authentication flow returns JWT token
2. **User sends message** → Frontend (`chat.js`) POSTs to `/chat` endpoint with `Authorization: Bearer <JWT>` header
3. **FastAPI app** (`app.py`) validates JWT, extracts user email as user_id
4. **Session manager** loads/creates conversation state from DynamoDB (or in-memory for local)
5. **NLU processing** (`openai_client.py`) uses OpenAI function calling to extract user intent
6. **Service execution** based on intent:
   - `search_products` → `CatalogService` queries UCP catalog or fallback products (public, no auth)
   - `add_to_cart` → `CheckoutService` creates/updates UCP checkout session (requires shopping assistant auth + merchant auth)
   - `complete_order` → `PaymentService` completes checkout with mock payment (requires both auth tokens)
7. **Merchant authorization** (on first cart operation):
   - Frontend redirects to merchant Auth0 for authorization
   - User approves, merchant Auth0 redirects back with authorization code
   - Backend exchanges code for access token using PKCE
   - Merchant token stored in session state
8. **State update** persisted to DynamoDB/in-memory
9. **Response** returned to frontend with bot message and conversation state

### Components

1. **Frontend** (`frontend/`)
   - Static HTML/CSS/JS chat interface with vanilla JavaScript
   - Auth0 SPA SDK for user authentication
   - Hosted on AWS Amplify
   - Communicates with Lambda via Function URL
   - Handles both shopping assistant login and merchant OAuth authorization

2. **Backend** (`src/chatbot/`)
   - FastAPI application wrapped with Mangum for Lambda
   - JWT validation for shopping assistant authentication
   - OpenAI NLU with function calling for intent recognition
   - UCP client for checkout operations
   - Merchant OAuth client for Authorization Code + PKCE flow
   - Dual session persistence: DynamoDB (production) + in-memory (local dev)

3. **Services**
   - `CatalogService`: Product search (UCP catalog API + hardcoded fallback) - public, no auth required
   - `CheckoutService`: Checkout workflow orchestration - requires shopping assistant auth
   - `PaymentService`: Payment completion with mock handler - requires both auth tokens

4. **Authentication** (`src/chatbot/auth/`)
   - JWT validator for shopping assistant tokens
   - Merchant OAuth client for PKCE authorization
   - FastAPI dependencies for protected endpoints
   - Webhook handlers for merchant authorization callbacks

### Key Architecture Patterns

- **Mangum adapter** (`main.py`): Wraps FastAPI app for Lambda execution
- **Environment detection** (`app.py`): Checks `AWS_EXECUTION_ENV` to use DynamoDB vs in-memory sessions
- **OpenAI function calling** (`nlu/tools.py`): System prompt + tool definitions extract structured intents
- **UCP client** (`ucp/client.py`): Handles all UCP API calls with required headers (UCP-Agent, request-signature, idempotency-key, request-id)
- **Conversation state** (`conversation/state.py`): Tracks checkout_id, line_items, buyer_info, fulfillment data

## Development Workflow

### Setup

```bash
# Create virtual environment (optional but recommended)
make venv
source venv/bin/activate

# Install dependencies for development
make dev

# Set up environment variables
cp .env.example .env
# Edit .env and add OPENAI_API_KEY (required)
```

### Local Development

```bash
# Run FastAPI locally with auto-reload
make local
# Access API at http://localhost:8000
# API docs at http://localhost:8000/docs

# Open frontend/index.html in browser to test chat UI
# (Frontend will auto-detect localhost API URL)
```

The Makefile detects if you're in a virtual environment and uses the appropriate Python/pip/uvicorn paths.

### Testing

```bash
# Run all tests
make test

# Run specific test file
pytest tests/test_ucp_client.py -v

# Run specific test
pytest tests/test_services.py::test_catalog_search -v

# Test with verbose output and stop on first failure
pytest tests/ -vsx
```

Tests use `pytest-asyncio` for async test support. Configuration in `pytest.ini`.

### Code Quality

```bash
# Format code with black
make format

# Lint code (ruff + mypy)
make lint
```

### Deployment

```bash
# Build SAM application (creates .aws-sam/build/)
make build

# Deploy to AWS (first time will prompt for config)
make deploy
# Stack Name: shopping-assistant-chatbot
# Region: us-east-1 (or your preference)
# OpenAIApiKey: [paste your key]
# Save arguments to samconfig.toml: y

# Deploy frontend to S3 (get bucket name from deployment outputs)
make deploy-frontend FRONTEND_BUCKET=your-bucket-name

# Clean build artifacts
make clean
```

## Key Files

### Core Application
- `src/chatbot/app.py` - FastAPI routes (`/chat`, `/session/new`, `/session/{id}`, `/discovery`)
- `src/chatbot/main.py` - Lambda handler (Mangum wrapper for FastAPI)
- `src/chatbot/config.py` - Pydantic settings with environment variable loading
- `src/chatbot/models.py` - Request/response models (ChatRequest, ChatResponse, etc.)

### NLU & Intent Recognition
- `src/chatbot/nlu/openai_client.py` - OpenAI client with function calling
- `src/chatbot/nlu/tools.py` - Function definitions and system prompt for intent extraction

### UCP Integration
- `src/chatbot/ucp/client.py` - UCP API client (discover, create_checkout, update_checkout, complete_checkout)
- `src/chatbot/ucp/headers.py` - UCP header generation (UCP-Agent, request-signature, etc.)

### Services
- `src/chatbot/services/catalog_service.py` - Product search with UCP catalog + hardcoded fallback
- `src/chatbot/services/checkout_service.py` - Cart management and checkout orchestration
- `src/chatbot/services/payment_service.py` - Payment completion with mock handler

### Session Management
- `src/chatbot/conversation/state.py` - ConversationState dataclass
- `src/chatbot/conversation/manager.py` - DynamoDB session persistence
- `src/chatbot/conversation/local_manager.py` - In-memory session storage for local dev

### Infrastructure
- `template.yaml` - AWS SAM template (Lambda, DynamoDB table, Function URL)
- `pyproject.toml` - Python dependencies and project metadata
- `requirements.txt` - Generated for Lambda layer

## UCP Happy Path Implementation

The chatbot implements the standard UCP checkout flow:

1. **Discovery** - GET /.well-known/ucp (cached for 5 minutes)
2. **Product Search** - Query UCP catalog API or use hardcoded fallback products
3. **Create Checkout** - POST /checkout-sessions with line items
4. **Update Cart** - PUT /checkout-sessions/{id} with updated items
5. **Apply Discounts** - PUT /checkout-sessions/{id} with discount codes
6. **Setup Fulfillment** - PUT /checkout-sessions/{id} with destinations and fulfillment methods
7. **Select Shipping** - Auto-selects first available shipping option
8. **Complete Order** - POST /checkout-sessions/{id}/complete with payment details

### UCP Client Details

All UCP requests include required headers:
- `UCP-Agent`: Points to agent profile URL (from `UCP_AGENT_PROFILE` env var)
- `request-signature`: UUID v4 signature
- `idempotency-key`: UUID v4 for idempotent requests
- `request-id`: UUID v4 for request tracking

The UCPClient (`ucp/client.py`) provides methods:
- `discover()` - Fetch UCP discovery document (with 5-minute cache)
- `create_checkout_with_payload()` - Create checkout with full payload
- `update_checkout()` - Update checkout with any fields
- `complete_checkout()` - Complete order with payment

## Authentication & Authorization

### Shopping Assistant Authentication (Auth0)

The shopping assistant uses Auth0 for user authentication with JWT tokens.

**Configuration:**
- **Domain**: grocery-b2c.cic-demo-platform.auth0app.com
- **Client ID**: 1vykALbEbAw4ltcrTMDnnRasNllHluqK
- **Application Type**: Single Page Application
- **User Identity**: Auth0 email is used as user_id

**Protected Endpoints** (require JWT):
- `POST /session/new` - Create new session
- `GET /session/{session_id}` - Get session
- `POST /chat` - Send chat message
- All cart/checkout operations

**Public Endpoints** (no auth):
- `GET /health`
- `GET /agent-profile`
- `GET /discovery`
- Product search via catalog API

**JWT Validation Flow:**
1. Frontend sends request with `Authorization: Bearer <JWT>` header
2. Backend validates JWT using Auth0 JWKS
3. Email extracted from JWT and used as user_id
4. User ownership verified for session operations

**Implementation:**
- `src/chatbot/auth/jwt_validator.py` - JWT validation with JWKS
- `src/chatbot/auth/dependencies.py` - FastAPI auth dependencies
- `frontend/chat.js` - Auth0 SPA SDK integration

### Merchant OAuth Authorization (PKCE)

The shopping assistant uses OAuth Authorization Code + PKCE to obtain merchant access tokens for UCP checkout operations.

**Configuration:**
- **Domain**: agentic-commerce-merchant.cic-demo-platform.auth0app.com
- **Client ID**: U5xtIqc7cu707C28nQHeCKplg9ec2VPe (shopping assistant's client ID)
- **Audience**: api://ucp.session.service
- **Scope**: openid profile email ucp:scopes:checkout_session
- **Redirect URI**: https://main.d7stwkdmkar4g.amplifyapp.com/auth/callback
- **Flow**: Authorization Code + PKCE (no client secret)

**Authorization Flow:**
1. User adds first item to cart (triggers merchant auth check)
2. Frontend checks merchant authorization status via `/webhooks/auth/status`
3. If not authorized, prompt user to "Connect Merchant Account"
4. User clicks "Connect" → initiate PKCE flow:
   - Frontend calls `/webhooks/auth/create` to generate authorization URL
   - Backend generates code_verifier and code_challenge
   - Frontend stores code_verifier in sessionStorage
   - User redirected to merchant Auth0 authorization endpoint
5. User approves authorization
6. Merchant Auth0 redirects back with authorization code
7. Frontend calls `/webhooks/auth/callback` with code and code_verifier
8. Backend exchanges code for access/refresh tokens using PKCE
9. Tokens stored in session state (DynamoDB)
10. User can now complete checkout with merchant token

**Intent Values** (Google Streamlined Identity pattern):
- `check` - Check if user has existing authorization (lightweight)
- `create` - Create new authorization (primary flow)
- `get` - Get existing authorization details

**Token Storage:**
Merchant tokens stored in `ConversationState.merchant_auth`:
```python
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": "2024-03-15T10:30:00Z",
  "merchant_user": {"email": "...", "name": "..."}
}
```

**Webhook Endpoints:**
- `GET /webhooks/auth/status` - Check merchant authorization status
- `POST /webhooks/auth/callback` - Handle OAuth callback
- `POST /webhooks/auth/create` - Initiate merchant authorization
- `GET /webhooks/auth/check` - Validate merchant token

**Implementation:**
- `src/chatbot/auth/merchant_oauth.py` - PKCE OAuth client
- `src/chatbot/webhooks/auth.py` - Webhook handlers
- `frontend/chat.js` - PKCE flow implementation with sessionStorage

### Token Refresh

**Shopping Assistant JWT:**
- Auth0 SPA SDK handles automatic token refresh
- Frontend catches 401 errors and refreshes token

**Merchant Access Token:**
- Backend checks token expiration before UCP calls
- Automatically refreshes using refresh_token if expired
- Updates session state with new tokens

## Important Implementation Details

### OpenAI Function Calling
- System prompt in `nlu/tools.py` includes critical intent recognition rules
- Key distinction: "show me X" = search only vs "add X" = search + add to cart
- Tools defined: `search_products`, `add_to_cart`, `update_cart_quantity`, `remove_from_cart`, `view_cart`, `apply_discount_code`, `complete_order`

### Session Management
- **Local dev**: In-memory session manager (no DynamoDB needed)
- **Production**: DynamoDB with TTL (30 days default)
- Environment detection via `AWS_EXECUTION_ENV` environment variable
- State includes: checkout_id, line_items, buyer_info, merchant_auth, fulfillment_destinations
- User sessions tied to email from JWT (user_id = email)

### Product Catalog
- Attempts to fetch from UCP catalog API first
- Falls back to hardcoded products if API unavailable
- Hardcoded products: bouquet_roses, pot_ceramic, bouquet_tulips, plant_succulent

### Payment Processing
- Uses mock payment handler (`success_token`)
- No real payment processing in MVP
- Auto-completes with mock payment on order completion

### Limitations
- Mock payment only
- Auto-selects first available shipping option
- No order history beyond current session
- Public Lambda Function URL (authentication at application level, not API Gateway)
