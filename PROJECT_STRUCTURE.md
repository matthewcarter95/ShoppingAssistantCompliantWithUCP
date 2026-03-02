# Project Structure

## Directory Tree

```
ShoppingAssistantCompliantWithUCP/
│
├── 📄 Configuration Files
│   ├── pyproject.toml              # Python package definition
│   ├── requirements.txt            # Lambda deployment requirements
│   ├── setup.py                    # Package setup script
│   ├── .env.example                # Environment variable template
│   ├── .gitignore                  # Git ignore patterns
│   ├── pytest.ini                  # Pytest configuration
│   └── samconfig.toml.example      # SAM CLI configuration example
│
├── 📄 Build & Deployment
│   ├── Makefile                    # Build and deployment commands
│   ├── template.yaml               # AWS SAM infrastructure definition
│   └── test_local.sh               # Local testing script
│
├── 📚 Documentation
│   ├── README.md                   # Main project documentation
│   ├── QUICKSTART.md               # 5-minute quick start guide
│   ├── DEPLOYMENT.md               # AWS deployment guide
│   ├── ARCHITECTURE.md             # System architecture details
│   ├── CLAUDE.md                   # AI assistant guidance
│   ├── IMPLEMENTATION_SUMMARY.md   # Implementation details
│   └── PROJECT_STATUS.md           # Current project status
│
├── 🎨 Frontend (3 files)
│   ├── index.html                  # Chat interface HTML
│   ├── style.css                   # Chat interface styling
│   └── chat.js                     # Frontend logic and API calls
│
├── 🐍 Backend Source (20 files)
│   └── src/chatbot/
│       ├── __init__.py             # Package initialization
│       ├── main.py                 # Lambda handler (Mangum wrapper)
│       ├── app.py                  # FastAPI application
│       ├── config.py               # Configuration management
│       ├── models.py               # API models (Pydantic)
│       │
│       ├── 🔌 ucp/                 # UCP Integration
│       │   ├── __init__.py
│       │   ├── client.py           # UCP API client
│       │   └── headers.py          # UCP header generation
│       │
│       ├── 🧠 nlu/                 # Natural Language Understanding
│       │   ├── __init__.py
│       │   ├── openai_client.py   # OpenAI API integration
│       │   └── tools.py            # Function calling definitions
│       │
│       ├── 🔧 services/            # Business Logic
│       │   ├── __init__.py
│       │   ├── catalog_service.py # Product search
│       │   ├── checkout_service.py # Checkout orchestration
│       │   └── payment_service.py # Payment completion
│       │
│       ├── 💬 conversation/        # Session Management
│       │   ├── __init__.py
│       │   ├── manager.py          # DynamoDB operations
│       │   └── state.py            # State data models
│       │
│       └── 🛠️ utils/               # Utilities
│           ├── __init__.py
│           └── logger.py           # Logging setup
│
└── 🧪 Tests (4 files)
    ├── __init__.py
    ├── conftest.py                 # Pytest configuration
    ├── test_ucp_client.py          # UCP client tests
    └── test_services.py            # Service tests
```

## Module Organization

### Layer 1: Entry Points
```
┌─────────────────────────────────────────────┐
│  main.py (Lambda Handler)                   │
│  ↓                                           │
│  app.py (FastAPI Routes)                    │
└─────────────────────────────────────────────┘
```

### Layer 2: Orchestration
```
┌─────────────────────────────────────────────┐
│  app.py (Request Handling)                  │
│  ├─> NLU Client (Intent Extraction)         │
│  ├─> Conversation Manager (State)           │
│  └─> Services (Business Logic)              │
└─────────────────────────────────────────────┘
```

### Layer 3: Business Logic
```
┌─────────────────────────────────────────────┐
│  services/catalog_service.py                │
│  services/checkout_service.py               │
│  services/payment_service.py                │
└─────────────────────────────────────────────┘
```

### Layer 4: External Integration
```
┌─────────────────────────────────────────────┐
│  ucp/client.py (UCP API)                    │
│  nlu/openai_client.py (OpenAI API)          │
│  conversation/manager.py (DynamoDB)         │
└─────────────────────────────────────────────┘
```

## File Descriptions

### Backend Files

| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | ~10 | Lambda entry point, Mangum wrapper |
| `app.py` | ~200 | FastAPI routes, chat logic, tool execution |
| `config.py` | ~40 | Configuration with Pydantic Settings |
| `models.py` | ~60 | API request/response models |
| `ucp/client.py` | ~170 | UCP API wrapper with all endpoints |
| `ucp/headers.py` | ~25 | UCP header generation |
| `nlu/openai_client.py` | ~100 | OpenAI integration with function calling |
| `nlu/tools.py` | ~90 | Function definitions and system prompt |
| `services/catalog_service.py` | ~100 | Product search with fallback |
| `services/checkout_service.py` | ~150 | Checkout workflow orchestration |
| `services/payment_service.py` | ~80 | Payment completion with address parsing |
| `conversation/manager.py` | ~100 | DynamoDB CRUD operations |
| `conversation/state.py` | ~80 | State data models |
| `utils/logger.py` | ~30 | Logging configuration |

**Total Backend**: ~1,235 lines of Python

### Frontend Files

| File | Lines | Purpose |
|------|-------|---------|
| `index.html` | ~50 | Chat UI structure |
| `style.css` | ~200 | Chat styling and animations |
| `chat.js` | ~180 | API calls, message rendering, state management |

**Total Frontend**: ~430 lines

### Infrastructure Files

| File | Lines | Purpose |
|------|-------|---------|
| `template.yaml` | ~110 | AWS SAM template (Lambda, DynamoDB, S3) |
| `Makefile` | ~50 | Build and deployment automation |

**Total Infrastructure**: ~160 lines

### Test Files

| File | Lines | Purpose |
|------|-------|---------|
| `test_ucp_client.py` | ~50 | UCP client unit tests |
| `test_services.py` | ~50 | Service layer unit tests |
| `test_local.sh` | ~80 | End-to-end integration testing |

**Total Tests**: ~180 lines

### Documentation Files

| File | Lines | Purpose |
|------|-------|---------|
| `README.md` | ~280 | Main documentation |
| `QUICKSTART.md` | ~130 | Quick start guide |
| `DEPLOYMENT.md` | ~350 | Deployment instructions |
| `ARCHITECTURE.md` | ~500 | Architecture documentation |
| `IMPLEMENTATION_SUMMARY.md` | ~300 | Implementation details |
| `PROJECT_STATUS.md` | ~250 | Project status |

**Total Documentation**: ~1,810 lines

## Total Project Size

- **Python Code**: ~1,235 lines
- **Frontend Code**: ~430 lines
- **Infrastructure**: ~160 lines
- **Tests**: ~180 lines
- **Documentation**: ~1,810 lines
- **Total**: ~3,815 lines

## Dependencies Graph

```
FastAPI Application (app.py)
    │
    ├─> NLU Client (nlu/openai_client.py)
    │       └─> OpenAI API
    │
    ├─> UCP Client (ucp/client.py)
    │       └─> UCP Merchant API
    │
    ├─> Conversation Manager (conversation/manager.py)
    │       └─> DynamoDB
    │
    └─> Services
            ├─> CatalogService
            │       └─> UCP Client
            ├─> CheckoutService
            │       └─> UCP Client
            └─> PaymentService
                    └─> UCP Client
```

## API Flow Diagram

```
User Message → Frontend (chat.js)
                    ↓
            POST /chat (app.py)
                    ↓
        Load Session (conversation/manager.py)
                    ↓
        Add Message to State
                    ↓
        Call OpenAI (nlu/openai_client.py)
                    ↓
        Extract Tool Calls
                    ↓
        ┌───────────┴───────────┐
        ↓                       ↓
   search_products        add_to_cart
        ↓                       ↓
   CatalogService        CheckoutService
        ↓                       ↓
   UCP Catalog API       UCP Checkout API
        ↓                       ↓
   Return Products       Return Cart Summary
        ↓                       ↓
        └───────────┬───────────┘
                    ↓
        Save Session (DynamoDB)
                    ↓
        Return Response
                    ↓
        Display (Frontend)
```

## Configuration Flow

```
.env file (local dev)
    ↓
config.py (Pydantic Settings)
    ↓
settings singleton
    ↓
    ├─> ucp/client.py (base_url, agent_profile)
    ├─> nlu/openai_client.py (api_key, model)
    ├─> conversation/manager.py (table_name, region)
    └─> utils/logger.py (log_level)
```

## Request/Response Examples

### Search Products
**Request**:
```json
POST /chat
{
  "session_id": "abc-123",
  "message": "Show me roses"
}
```

**Response**:
```json
{
  "text": "Here are some beautiful roses...",
  "results": [
    {
      "id": "bouquet_roses",
      "name": "Red Rose Bouquet",
      "description": "A beautiful bouquet of 12 red roses",
      "price": 49.99,
      "currency": "USD"
    }
  ],
  "checkout_summary": null,
  "order": null
}
```

### Add to Cart
**Request**:
```json
POST /chat
{
  "session_id": "abc-123",
  "message": "Add the red rose bouquet"
}
```

**Response**:
```json
{
  "text": "I've added Red Rose Bouquet to your cart!",
  "results": [],
  "checkout_summary": {
    "checkout_id": "checkout_xyz",
    "line_items": [
      {"product_id": "bouquet_roses", "quantity": 1}
    ],
    "total": {"amount": "49.99", "currency": "USD"}
  },
  "order": null
}
```

### Complete Order
**Request**:
```json
POST /chat
{
  "session_id": "abc-123",
  "message": "Complete order. John Doe, john@example.com, 123 Main St, Anytown CA 12345"
}
```

**Response**:
```json
{
  "text": "Your order is complete!",
  "results": [],
  "checkout_summary": null,
  "order": {
    "id": "order_123",
    "status": "confirmed",
    "permalink_url": "https://merchant.example/orders/order_123",
    "total": {"amount": "49.99", "currency": "USD"}
  }
}
```

## Deployment Architecture

### Development Environment
```
Local Machine
    ├── Python 3.11+
    ├── Virtual Environment
    ├── .env file (with OPENAI_API_KEY)
    ├── uvicorn (FastAPI dev server)
    └── Browser (opens frontend/index.html)
```

### Production Environment
```
AWS Cloud
    ├── Lambda Function
    │   ├── Python 3.11 runtime
    │   ├── FastAPI + Mangum
    │   ├── Environment Variables
    │   ├── IAM Role (DynamoDB access)
    │   └── Function URL (public HTTPS)
    │
    ├── DynamoDB Table
    │   ├── ConversationSessions
    │   ├── On-demand billing
    │   └── TTL enabled
    │
    └── S3 Bucket
        ├── Static website hosting
        ├── Public read access
        └── Frontend files (HTML/JS/CSS)
```

## Key Relationships

### Client Initialization Flow
```python
# In app.py
ucp_client = UCPClient()                          # UCP API client
nlu_client = NLUClient()                          # OpenAI client
conversation_manager = ConversationManager()      # DynamoDB client

catalog_service = CatalogService(ucp_client)      # Inject UCP client
checkout_service = CheckoutService(ucp_client)    # Inject UCP client
payment_service = PaymentService(ucp_client)      # Inject UCP client
```

### Service Dependencies
```
CatalogService
    └─> UCPClient
            └─> httpx.AsyncClient

CheckoutService
    └─> UCPClient
            └─> httpx.AsyncClient

PaymentService
    └─> UCPClient
            └─> httpx.AsyncClient

NLUClient
    └─> AsyncOpenAI
            └─> OpenAI API

ConversationManager
    └─> boto3.DynamoDB
            └─> AWS DynamoDB
```

## Import Hierarchy

```
main.py
    └─> app.py
            ├─> config.py
            ├─> models.py
            ├─> ucp/client.py
            │       └─> ucp/headers.py
            ├─> nlu/openai_client.py
            │       └─> nlu/tools.py
            ├─> conversation/manager.py
            │       └─> conversation/state.py
            ├─> services/catalog_service.py
            ├─> services/checkout_service.py
            ├─> services/payment_service.py
            └─> utils/logger.py
```

## Environment-Specific Behavior

### Local Development
- Loads .env file
- Uses localhost URLs
- FastAPI dev server (uvicorn)
- Direct file access for frontend

### AWS Lambda
- Environment variables from template.yaml
- Function URL for API access
- S3 for frontend hosting
- CloudWatch for logs

## Quick Reference

### Start Development
```bash
make dev          # Install dependencies
make local        # Start local server
```

### Run Tests
```bash
make test         # Unit tests
./test_local.sh   # Integration tests
```

### Deploy
```bash
make build        # Build SAM app
make deploy       # Deploy to AWS
make deploy-frontend FRONTEND_BUCKET=name  # Deploy frontend
```

### Clean
```bash
make clean        # Remove build artifacts
```

### View Logs (AWS)
```bash
sam logs -n ChatbotFunction --tail
```

## File Size Estimates

- **Backend**: ~35 KB (Python source)
- **Frontend**: ~15 KB (HTML/JS/CSS)
- **Tests**: ~8 KB
- **Documentation**: ~45 KB
- **Configuration**: ~5 KB

**Total Repository**: ~108 KB (excluding dependencies)

**Lambda Package** (with dependencies): ~30 MB

## Critical Paths

### Chat Request Critical Path
1. API Gateway/Function URL receives request
2. Mangum routes to FastAPI
3. Load session from DynamoDB (~50ms)
4. Call OpenAI API (~1-2 seconds)
5. Execute tool calls (~200-500ms per UCP call)
6. Save session to DynamoDB (~50ms)
7. Return response

**Total**: ~2-4 seconds

### Bottlenecks
- ⚠️ OpenAI API latency (largest contributor)
- Cold Lambda start (~2-3 seconds first request)
- Multiple UCP API calls (sequential)

### Optimization Opportunities
- Cache OpenAI responses for common queries
- Parallel UCP API calls where possible
- Use Lambda provisioned concurrency
- Pre-warm connections
