# Quick Start Guide

Get the Shopping Assistant Chatbot running in 5 minutes.

## Local Development

### 1. Install Dependencies

```bash
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and add: OPENAI_API_KEY=sk-your-key-here
```

### 3. Run

```bash
make local
```

### 4. Test

Open `frontend/index.html` in your browser and start chatting.

Or use curl:

```bash
# Health check
curl http://localhost:8000/health

# Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-123",
    "message": "Show me roses"
  }'
```

## AWS Deployment

### 1. Prerequisites

```bash
# Install AWS SAM CLI
brew install aws-sam-cli  # macOS
# or follow: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html

# Configure AWS credentials
aws configure
```

### 2. Build and Deploy

```bash
# Build
make build

# Deploy (follow prompts)
make deploy
```

When prompted:
- **OpenAIApiKey**: Paste your OpenAI API key
- Accept defaults for other settings
- Confirm deployment

### 3. Deploy Frontend

```bash
# Use bucket name from deployment outputs
make deploy-frontend FRONTEND_BUCKET=shopping-assistant-frontend-YOUR_ACCOUNT_ID
```

### 4. Access

Open the Frontend Bucket URL from deployment outputs.

## Test Conversation

Try this conversation flow:

```
You: Show me roses
Bot: [Shows rose products]

You: Add the red rose bouquet to my cart
Bot: [Confirms item added, shows cart]

You: Add 2 ceramic pots
Bot: [Updates cart]

You: Apply code 10OFF
Bot: [Applies discount]

You: Complete my order. John Doe, john@example.com, 123 Main St, Anytown CA 12345
Bot: [Shows order confirmation]
```

## Common Commands

```bash
make local              # Run locally
make test               # Run tests
make build              # Build for AWS
make deploy             # Deploy to AWS
make clean              # Clean build artifacts
make help               # Show all commands
```

## Troubleshooting

**OpenAI errors**: Check API key in .env or Lambda environment variables

**UCP errors**: Verify merchant API is accessible:
```bash
curl https://n5je6mqzsskozc32cqdfetl42q0augte.lambda-url.us-east-1.on.aws/.well-known/ucp
```

**Lambda timeout**: Increase timeout in template.yaml, redeploy

**CORS errors**: Check Lambda Function URL CORS configuration in template.yaml

## Next Steps

- Review [README.md](README.md) for detailed documentation
- Review [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment guide
- Add custom products to catalog
- Implement real payment handlers
- Add user authentication
