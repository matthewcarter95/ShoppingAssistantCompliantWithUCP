# Architecture Documentation

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          User's Browser                              │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │              S3 Static Website (Frontend)                   │    │
│  │  - index.html: Chat interface                              │    │
│  │  - chat.js: API integration                                │    │
│  │  - style.css: UI styling                                   │    │
│  └──────────────────────┬─────────────────────────────────────┘    │
└─────────────────────────┼──────────────────────────────────────────┘
                          │ HTTPS
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AWS Lambda (Function URL)                         │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │         FastAPI + Mangum (main.py, app.py)                 │    │
│  │                                                             │    │
│  │  Endpoints:                                                │    │
│  │  - POST /chat           - Main conversation endpoint       │    │
│  │  - GET /discovery       - UCP discovery                    │    │
│  │  - POST /session/new    - Create session                   │    │
│  │  - GET /session/{id}    - Get session                      │    │
│  │  - GET /health          - Health check                     │    │
│  └──────────────┬────────────────┬──────────────┬─────────────┘    │
└─────────────────┼────────────────┼──────────────┼──────────────────┘
                  │                │              │
                  ▼                ▼              ▼
    ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐
    │   OpenAI API    │  │  UCP Merchant│  │   DynamoDB     │
    │                 │  │     API      │  │                │
    │  - GPT-3.5      │  │              │  │ - Sessions     │
    │  - Function     │  │  - Checkout  │  │ - Conversation │
    │    Calling      │  │  - Catalog   │  │   History      │
    │  - NLU          │  │  - Payment   │  │ - Cart State   │
    └─────────────────┘  └──────────────┘  └────────────────┘
```

## Component Breakdown

### Frontend Layer

**Files**: `frontend/index.html`, `frontend/chat.js`, `frontend/style.css`

**Responsibilities**:
- User interface for chat interaction
- Message display and formatting
- Product card rendering
- Cart summary visualization
- Session management (localStorage)
- API communication

**Key Features**:
- Responsive design
- Real-time message updates
- Auto-scrolling chat
- Product card display
- Order confirmation view

### API Layer

**Files**: `src/chatbot/app.py`, `src/chatbot/main.py`, `src/chatbot/models.py`

**Responsibilities**:
- HTTP request handling
- Request validation
- Response formatting
- CORS management
- Error handling
- Lambda integration

**Endpoints**:
```
POST   /chat            - Process user messages
GET    /discovery       - Return UCP discovery doc
POST   /session/new     - Create new session
GET    /session/{id}    - Retrieve session state
GET    /health          - Health check
```

### NLU Layer

**Files**: `src/chatbot/nlu/openai_client.py`, `src/chatbot/nlu/tools.py`

**Responsibilities**:
- Natural language understanding
- Intent extraction
- Function calling orchestration
- Conversation context management

**Functions Supported**:
1. `search_products(query)` - Search catalog
2. `add_to_cart(product_id, quantity)` - Add items
3. `apply_discount_code(code)` - Apply discounts
4. `complete_order(buyer_name, buyer_email, shipping_address)` - Checkout

### Service Layer

**Files**: `src/chatbot/services/*.py`

**Components**:

1. **CatalogService** (`catalog_service.py`)
   - Product search via UCP API
   - Hardcoded product fallback
   - Product lookup by ID

2. **CheckoutService** (`checkout_service.py`)
   - Checkout session creation
   - Line item management
   - Discount application
   - Fulfillment setup

3. **PaymentService** (`payment_service.py`)
   - Payment completion
   - Address parsing
   - Mock payment handler

### UCP Integration Layer

**Files**: `src/chatbot/ucp/client.py`, `src/chatbot/ucp/headers.py`

**Responsibilities**:
- UCP API communication
- Header generation (UCP-Agent, idempotency-key, etc.)
- Discovery document caching
- Checkout session management
- Error handling and retries

**UCP Endpoints Used**:
```
GET    /.well-known/ucp                      - Discovery
GET    /products?q={query}                   - Catalog search
POST   /checkout-sessions                    - Create checkout
PUT    /checkout-sessions/{id}               - Update checkout
POST   /checkout-sessions/{id}/complete      - Complete order
GET    /checkout-sessions/{id}               - Get checkout
```

### Data Layer

**Files**: `src/chatbot/conversation/manager.py`, `src/chatbot/conversation/state.py`

**Responsibilities**:
- Session persistence
- Conversation history storage
- State management
- Automatic expiration (TTL)

**Data Model**:
```python
ConversationState:
  - user_id: str
  - session_id: str
  - checkout_id: Optional[str]
  - line_items: List[Dict]
  - buyer_info: Optional[Dict]
  - messages: List[Message]
  - status: str (init → shopping → ready_to_pay → completed)
  - timestamps: created_at, updated_at, ttl
```

### Configuration Layer

**Files**: `src/chatbot/config.py`

**Responsibilities**:
- Environment variable management
- Settings validation
- Default values
- Type safety

**Configuration Keys**:
- `OPENAI_API_KEY` (required)
- `UCP_BASE_URL` (default provided)
- `CHATBOT_MODEL` (default: gpt-3.5-turbo)
- `DYNAMODB_TABLE` (default: ConversationSessions)
- `LOG_LEVEL` (default: INFO)

## Data Flow

### Chat Request Flow

```
1. User types message → Frontend (chat.js)
2. POST /chat → Lambda (app.py)
3. Load session → DynamoDB (manager.py)
4. Add user message → ConversationState
5. Format messages → NLU Client (openai_client.py)
6. Call OpenAI API → Function calling response
7. Execute tool calls:
   a. search_products → CatalogService → UCP API
   b. add_to_cart → CheckoutService → UCP API
   c. apply_discount_code → CheckoutService → UCP API
   d. complete_order → PaymentService → UCP API
8. Add assistant message → ConversationState
9. Save session → DynamoDB
10. Return response → Frontend
11. Display messages, products, cart → User
```

### UCP Checkout Flow

```
Step 1: Search Products
  └─> GET /products?q=roses

Step 2: Create Checkout
  └─> POST /checkout-sessions
      Body: { line_items: [...] }

Step 3: Update Cart
  └─> PUT /checkout-sessions/{id}
      Body: { line_items: [...] }

Step 4: Apply Discount
  └─> PUT /checkout-sessions/{id}
      Body: { discounts: [{code: "10OFF"}] }

Step 5: Setup Fulfillment
  └─> PUT /checkout-sessions/{id}
      Body: { fulfillment: { methods: ["delivery"], destinations: [...] } }

Step 6: Select Shipping
  └─> PUT /checkout-sessions/{id}
      Body: { fulfillment: { selection: "option_1" } }

Step 7: Complete Order
  └─> POST /checkout-sessions/{id}/complete
      Body: { payment_instrument: {...}, buyer: {...} }
```

## AWS Infrastructure

### Lambda Function

**Configuration**:
- Runtime: Python 3.11
- Memory: 512 MB
- Timeout: 30 seconds
- Handler: src.chatbot.main.lambda_handler
- Function URL: Enabled with CORS

**Environment Variables**:
- OPENAI_API_KEY
- UCP_BASE_URL
- DYNAMODB_TABLE
- LOG_LEVEL

**IAM Permissions**:
- DynamoDB: GetItem, PutItem, Query, Scan
- CloudWatch: CreateLogGroup, CreateLogStream, PutLogEvents

### DynamoDB Table

**Configuration**:
- Name: ConversationSessions
- Billing: On-demand
- Keys: user_id (HASH), session_id (RANGE)
- TTL: Enabled on 'ttl' attribute

**Indexes**: None (simple key-value lookup)

### S3 Bucket

**Configuration**:
- Name: shopping-assistant-frontend-{account-id}
- Website Hosting: Enabled
- Public Access: Enabled for website
- CORS: Allowed for Lambda URL

**Contents**:
- index.html
- chat.js
- style.css

## Error Handling Strategy

### API Layer Errors
- 400: Invalid request (validation errors)
- 404: Session not found
- 500: Internal server errors

### Service Layer Errors
- Log errors with context
- Return user-friendly messages
- Fallback mechanisms (e.g., hardcoded catalog)
- Continue processing other tool calls

### UCP API Errors
- Retry with exponential backoff
- Log full request/response for debugging
- Return error to user with actionable message

### OpenAI API Errors
- Rate limiting: Wait and retry
- Token limit: Truncate conversation history
- API down: Return fallback message

## Logging Strategy

### Log Levels

**INFO**: Normal operations
- Session creation
- UCP API calls
- OpenAI API calls
- Checkout operations

**DEBUG**: Detailed information
- Message formatting
- Cache hits
- Discovery document retrieval

**WARNING**: Potential issues
- Catalog API fallback
- Missing optional fields

**ERROR**: Failures
- API call failures
- Database errors
- Unexpected exceptions

### Log Format

```
2024-01-15 10:30:45 - chatbot.app - INFO - Created session abc-123 for user test_user
2024-01-15 10:30:46 - chatbot.nlu.openai_client - INFO - OpenAI returned 1 tool calls
2024-01-15 10:30:47 - chatbot.ucp.client - INFO - Fetched UCP discovery document
```

## Monitoring Recommendations

### Key Metrics to Track

1. **Request Volume**
   - Total chat requests
   - Requests per session
   - New sessions created

2. **Latency**
   - Lambda duration
   - OpenAI API latency
   - UCP API latency
   - End-to-end request time

3. **Error Rates**
   - Lambda errors
   - OpenAI API errors
   - UCP API errors
   - Client-side errors

4. **Business Metrics**
   - Checkout sessions created
   - Orders completed
   - Average items per order
   - Discount code usage

### CloudWatch Dashboards

Create dashboard with widgets for:
- Lambda invocations (line chart)
- Lambda errors (line chart)
- Lambda duration (line chart)
- DynamoDB read/write capacity (line chart)
- Conversation completion rate (metric math)

## Scalability Considerations

### Current Capacity

**Lambda**:
- Concurrent executions: 1000 (default AWS account limit)
- Can handle ~10K requests/minute

**DynamoDB**:
- On-demand billing: Auto-scales
- Can handle millions of requests/second

**OpenAI**:
- Rate limits depend on tier (typically 3500 requests/minute)
- Consider caching common queries

### Scaling Strategies

1. **Increase Lambda concurrency** - Request limit increase from AWS
2. **Add caching layer** - Redis/ElastiCache for frequent queries
3. **OpenAI response caching** - Cache similar queries
4. **DynamoDB optimization** - Add GSI for common query patterns
5. **CDN for frontend** - CloudFront in front of S3

## Security Architecture

### Current Security Model

```
[Public Internet]
       ↓
[No Authentication] ← ⚠️ MVP only
       ↓
[Lambda Function URL]
       ↓
[IAM Role] → [DynamoDB]
       ↓
[Environment Variables] → [OpenAI API Key] ← ⚠️ Should use Secrets Manager
       ↓
[HTTPS] → [UCP Merchant API]
```

### Recommended Production Security

```
[Public Internet]
       ↓
[AWS WAF] ← Rate limiting, IP filtering
       ↓
[API Gateway] ← API keys or JWT validation
       ↓
[Lambda Authorizer] ← Custom auth logic
       ↓
[Lambda Function (VPC)] ← Network isolation
       ↓
[IAM Role] → [DynamoDB with encryption]
       ↓
[Secrets Manager] → [OpenAI API Key] ← Secure storage
       ↓
[HTTPS with mTLS] → [UCP Merchant API]
```

## Technology Decisions Rationale

### Why FastAPI?
- Modern async Python framework
- Automatic OpenAPI documentation
- Pydantic integration for validation
- High performance
- Easy to test

### Why Mangum?
- Seamless FastAPI → Lambda adapter
- No code changes needed
- Handles API Gateway and Function URL events
- Lightweight

### Why OpenAI Function Calling?
- Native structured output
- Better than prompt engineering
- Handles ambiguous intents
- Easy to extend with new functions

### Why DynamoDB?
- Serverless (no server management)
- Auto-scaling
- Built-in TTL for session expiration
- Low latency
- Cost-effective for this use case

### Why Lambda Function URL?
- Simpler than API Gateway
- Lower latency
- Built-in CORS
- No additional cost
- Sufficient for MVP

### Why S3 Static Website?
- Simple frontend hosting
- No server needed
- Very low cost
- Fast delivery
- Easy to update

## Extension Points

### Adding New Products

Edit `src/chatbot/services/catalog_service.py`:

```python
HARDCODED_PRODUCTS = [
    # Add new products here
    {
        "id": "your_product_id",
        "name": "Product Name",
        "description": "Description",
        "price": 29.99,
        "currency": "USD",
    },
]
```

### Adding New Intents

1. Define function in `src/chatbot/nlu/tools.py`:
```python
{
    "type": "function",
    "function": {
        "name": "your_new_function",
        "description": "What it does",
        "parameters": {...}
    }
}
```

2. Handle in `src/chatbot/app.py` chat endpoint:
```python
elif tool_name == "your_new_function":
    # Implementation
```

### Integrating Real Payment Handler

Replace mock handler in `src/chatbot/services/payment_service.py`:

```python
payment_instrument = {
    "type": "CardPaymentInstrument",
    "payment_handler": "stripe_payment_handler",  # Real handler
    "token": stripe_payment_token,  # From Stripe.js
    "billing_address": {...}
}
```

### Adding User Authentication

1. Add Cognito User Pool to `template.yaml`
2. Add Lambda Authorizer
3. Extract user_id from JWT token
4. Update frontend to include auth token

### Adding More UCP Features

The UCP client (`src/chatbot/ucp/client.py`) can be extended to support:
- Order tracking: `GET /orders/{id}`
- Order history: `GET /orders`
- Product details: `GET /products/{id}`
- Inventory check: `GET /products/{id}/inventory`
- Returns/refunds: `POST /orders/{id}/return`

## Performance Optimization

### Current Optimizations

1. **Discovery Caching** - Cache UCP discovery for 5 minutes
2. **Async/Await** - Non-blocking I/O throughout
3. **Connection Pooling** - httpx reuses connections
4. **Minimal Dependencies** - Small Lambda package

### Future Optimizations

1. **Response Streaming** - Stream OpenAI responses to user
2. **Lazy Loading** - Load services on-demand
3. **Lambda Layers** - Move dependencies to layer
4. **Provisioned Concurrency** - Eliminate cold starts
5. **Product Caching** - Cache catalog responses
6. **DynamoDB DAX** - In-memory cache for sessions

## Maintenance

### Regular Tasks

**Daily**:
- Monitor CloudWatch alarms
- Check error rates in logs

**Weekly**:
- Review conversation logs for improvements
- Update hardcoded products if needed
- Check OpenAI API usage and costs

**Monthly**:
- Update dependencies (security patches)
- Review AWS costs
- Analyze user conversation patterns
- Update function calling prompts

### Update Process

**Backend Changes**:
```bash
# Make changes to src/chatbot/
make build
sam deploy
```

**Frontend Changes**:
```bash
# Make changes to frontend/
make deploy-frontend FRONTEND_BUCKET=your-bucket
```

**Configuration Changes**:
```bash
# Update template.yaml
sam deploy
```

### Rollback Process

```bash
# Rollback to previous version
aws cloudformation describe-stacks \
  --stack-name shopping-assistant-chatbot \
  --query 'Stacks[0].Outputs'

# If needed, redeploy previous version
git checkout <previous-commit>
make build
sam deploy
```

## Testing Strategy

### Unit Tests
- Mock external dependencies (OpenAI, UCP, DynamoDB)
- Test business logic in isolation
- Run with: `make test`

### Integration Tests
- Test against local FastAPI server
- Use real APIs (with test keys)
- Run with: `./test_local.sh`

### End-to-End Tests
- Test deployed application
- Use real frontend interface
- Verify complete user journeys

### Load Tests
```bash
# Example with Apache Bench
ab -n 1000 -c 10 -p request.json -T application/json \
  https://your-lambda-url/chat
```

## Disaster Recovery

### Backup Strategy

**DynamoDB**:
- Enable Point-in-Time Recovery
- Automated backups to S3

**Lambda Code**:
- Version control with Git
- Tagged releases
- S3 deployment packages

**Frontend**:
- Version control with Git
- S3 versioning enabled

### Recovery Procedures

**Lost DynamoDB Data**:
```bash
# Restore from backup
aws dynamodb restore-table-from-backup \
  --target-table-name ConversationSessions \
  --backup-arn arn:aws:dynamodb:...
```

**Corrupted Lambda**:
```bash
# Redeploy from Git
git checkout main
make build
sam deploy
```

**S3 Frontend Issues**:
```bash
# Redeploy frontend
make deploy-frontend FRONTEND_BUCKET=your-bucket
```
