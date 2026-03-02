# Shopping Assistant Chatbot - UCP Compliant

A conversational shopping assistant that integrates with UCP (Universal Commerce Protocol) services, uses OpenAI for natural language understanding, and deploys to AWS as a serverless application.

## Features

- Natural language product search
- Conversational cart management
- Discount code application
- UCP-compliant checkout flow
- Mock payment processing
- Serverless deployment on AWS Lambda
- DynamoDB session persistence
- Simple chat UI

## Architecture

```
[S3 Static Website - Chat UI]
         |
         v
[API Gateway / Lambda Function URL]
         |
         v
[FastAPI Application (Mangum)]
  ├── OpenAI NLU (function calling)
  ├── UCP Client (calls merchant API)
  ├── Conversation Manager
  └── DynamoDB (session state)
         |
         v
[UCP Merchant API]
```

## Prerequisites

- Python 3.11+
- AWS CLI configured with credentials
- AWS SAM CLI
- OpenAI API key
- Node.js (optional, for local frontend dev)

## Setup

### 1. Clone and Install Dependencies

```bash
# Install Python dependencies
make install

# For development
make dev
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your OpenAI API key
# OPENAI_API_KEY=sk-your-key-here
```

### 3. Local Development

```bash
# Run FastAPI locally
make local

# The API will be available at http://localhost:8000
# Open frontend/index.html in a browser to test
```

### 4. Deploy to AWS

```bash
# Build the SAM application
make build

# Deploy (first time - will prompt for configuration)
make deploy

# Follow the prompts:
# - Stack Name: shopping-assistant-chatbot
# - AWS Region: us-east-1 (or your preferred region)
# - Parameter OpenAIApiKey: (paste your OpenAI API key)
# - Confirm changes and allow IAM role creation

# Note the outputs:
# - ChatbotFunctionUrl: Your Lambda function URL
# - FrontendBucketUrl: Your S3 website URL
```

### 5. Deploy Frontend

```bash
# Update frontend/chat.js with your Lambda Function URL if needed
# (It should auto-detect in production)

# Deploy frontend to S3
make deploy-frontend FRONTEND_BUCKET=shopping-assistant-frontend-YOUR_ACCOUNT_ID
```

## Usage

### Web Interface

1. Open the Frontend Bucket URL from the deployment outputs
2. Start chatting with the assistant
3. Try commands like:
   - "Show me roses"
   - "Add the red rose bouquet to my cart"
   - "Apply code 10OFF"
   - "Complete my order with name John Doe, email john@example.com, address 123 Main St, Anytown CA 12345"

### API Endpoints

**POST /chat**
```bash
curl -X POST https://your-lambda-url/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session",
    "user_id": "default_user",
    "message": "Show me roses"
  }'
```

**GET /discovery**
```bash
curl https://your-lambda-url/discovery
```

**POST /session/new**
```bash
curl -X POST https://your-lambda-url/session/new \
  -H "Content-Type: application/json" \
  -d '{"user_id": "default_user"}'
```

**GET /session/{session_id}**
```bash
curl https://your-lambda-url/session/test-session?user_id=default_user
```

## Happy Path Flow

1. User: "Show me roses"
   - Searches products via UCP catalog or fallback
   - Returns product listings

2. User: "Add the red rose bouquet to my cart"
   - Creates UCP checkout session
   - Adds item to cart
   - Shows cart summary

3. User: "Add 2 ceramic pots"
   - Updates checkout with additional items
   - Shows updated cart

4. User: "Apply code 10OFF"
   - Applies discount to checkout
   - Shows updated total

5. User: "Complete my order. John Doe, john@example.com, 123 Main St, Anytown CA 12345"
   - Extracts buyer information
   - Sets up fulfillment
   - Completes checkout with mock payment
   - Returns order confirmation

## Development

### Run Tests

```bash
make test
```

### Format Code

```bash
make format
```

### Lint Code

```bash
make lint
```

### Clean Build Artifacts

```bash
make clean
```

## Project Structure

```
ShoppingAssistantCompliantWithUCP/
├── src/chatbot/              # Backend application
│   ├── main.py               # Lambda handler
│   ├── app.py                # FastAPI application
│   ├── config.py             # Configuration
│   ├── models.py             # API models
│   ├── ucp/                  # UCP integration
│   ├── nlu/                  # OpenAI NLU
│   ├── services/             # Business logic
│   ├── conversation/         # Session management
│   └── utils/                # Utilities
├── frontend/                 # Chat UI
│   ├── index.html
│   ├── style.css
│   └── chat.js
├── tests/                    # Unit tests
├── template.yaml             # SAM template
├── pyproject.toml            # Python dependencies
├── requirements.txt          # Lambda requirements
└── Makefile                  # Build commands
```

## Configuration

Environment variables (in `.env` for local, or Lambda environment):

- `OPENAI_API_KEY` (required): Your OpenAI API key
- `UCP_BASE_URL`: UCP merchant API base URL
- `CHATBOT_MODEL`: OpenAI model to use (default: gpt-3.5-turbo)
- `DYNAMODB_TABLE`: DynamoDB table name (default: ConversationSessions)
- `LOG_LEVEL`: Logging level (default: INFO)

## UCP Integration

The chatbot implements the UCP happy path:

1. Discovery: `GET /.well-known/ucp`
2. Create checkout: `POST /checkout-sessions`
3. Update checkout: `PUT /checkout-sessions/{id}`
4. Setup fulfillment: `PUT /checkout-sessions/{id}` with fulfillment data
5. Complete checkout: `POST /checkout-sessions/{id}/complete`

All requests include required UCP headers:
- `UCP-Agent`
- `request-signature`
- `idempotency-key`
- `request-id`

## License

MIT
