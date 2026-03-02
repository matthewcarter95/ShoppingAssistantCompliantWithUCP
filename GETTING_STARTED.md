# Getting Started Checklist

Follow this checklist to get your Shopping Assistant Chatbot up and running.

## Prerequisites Checklist

- [ ] Python 3.11 or higher installed
  ```bash
  python3 --version  # Should show 3.11+
  ```

- [ ] AWS CLI installed and configured
  ```bash
  aws --version
  aws configure list  # Verify credentials
  ```

- [ ] AWS SAM CLI installed
  ```bash
  sam --version  # Should show 1.0+
  ```

- [ ] OpenAI API key obtained
  - Sign up at https://platform.openai.com
  - Create API key at https://platform.openai.com/api-keys
  - Keep it secure!

## Local Development Setup

### Step 1: Install Dependencies

```bash
# Install with development tools
make dev

# Or just production dependencies
make install
```

Expected output: "Successfully installed fastapi mangum httpx..."

### Step 2: Configure Environment

```bash
# Copy example configuration
cp .env.example .env

# Edit .env file
nano .env
# or
code .env
# or
vim .env
```

Add your OpenAI API key:
```
OPENAI_API_KEY=sk-proj-...your-actual-key...
```

### Step 3: Verify Configuration

```bash
# Check if .env is configured
grep "OPENAI_API_KEY" .env
```

Should show: `OPENAI_API_KEY=sk-proj-...`

### Step 4: Start Local Server

```bash
make local
```

Expected output:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Step 5: Test API (New Terminal)

```bash
# Health check
curl http://localhost:8000/health

# Expected: {"status":"healthy"}

# Discovery
curl http://localhost:8000/discovery | jq .

# Create session
curl -X POST http://localhost:8000/session/new \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user"}' | jq .

# Expected: {"session_id":"...","user_id":"test_user"}
```

### Step 6: Test Chat Interface

```bash
# Open frontend in browser
open frontend/index.html
# or on Linux: xdg-open frontend/index.html
```

Try chatting:
- "Show me roses"
- "Add the red rose bouquet"

### Step 7: Run Test Suite

```bash
# Run unit tests
make test

# Run integration tests (requires local server running)
./test_local.sh
```

## AWS Deployment Setup

### Step 1: Verify AWS Access

```bash
# Check AWS credentials
aws sts get-caller-identity

# Expected: Shows your AWS account ID and user ARN
```

### Step 2: Build Application

```bash
make build
```

Expected output:
```
Building codeuri: /path/to/project runtime: python3.11...
Build Succeeded
```

### Step 3: Deploy to AWS

```bash
make deploy
```

You'll be prompted for:

**Prompts and Recommended Answers**:

| Prompt | Recommended Answer | Notes |
|--------|-------------------|-------|
| Stack Name | `shopping-assistant-chatbot` | Or your preferred name |
| AWS Region | `us-east-1` | Or your preferred region |
| Parameter OpenAIApiKey | `sk-proj-...` | Paste your OpenAI API key |
| Confirm changes before deploy | `Y` | Review resources first |
| Allow SAM CLI IAM role creation | `Y` | Required for DynamoDB access |
| Disable rollback | `N` | Keep rollback enabled |
| Save arguments to config file | `Y` | Saves for next deployment |
| SAM configuration file | `samconfig.toml` | Default is fine |
| SAM configuration environment | `default` | Default is fine |

Deployment takes 2-5 minutes.

### Step 4: Note Outputs

After deployment, save these values:

```bash
# ChatbotFunctionUrl
https://abc123xyz.lambda-url.us-east-1.on.aws/

# FrontendBucketUrl
http://shopping-assistant-frontend-123456789012.s3-website-us-east-1.amazonaws.com

# DynamoDBTable
ConversationSessions
```

### Step 5: Test Deployed API

```bash
# Replace with your actual Function URL
LAMBDA_URL="https://abc123xyz.lambda-url.us-east-1.on.aws"

# Health check
curl $LAMBDA_URL/health

# Discovery
curl $LAMBDA_URL/discovery | jq .

# Chat test
curl -X POST $LAMBDA_URL/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test-123","message":"Show me roses"}' | jq .
```

### Step 6: Deploy Frontend

```bash
# Get your AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Deploy frontend
make deploy-frontend FRONTEND_BUCKET=shopping-assistant-frontend-$ACCOUNT_ID
```

Expected output: "upload: frontend/index.html to s3://..."

### Step 7: Access Application

Open the Frontend Bucket URL from Step 4 in your browser.

Example: http://shopping-assistant-frontend-123456789012.s3-website-us-east-1.amazonaws.com

## Verification Checklist

### Local Development

- [ ] Dependencies installed without errors
- [ ] .env file configured with OpenAI API key
- [ ] Local server starts successfully
- [ ] Health check returns {"status":"healthy"}
- [ ] Discovery endpoint returns UCP document
- [ ] Frontend loads in browser
- [ ] Can send chat messages
- [ ] Receives responses from assistant
- [ ] Product search works
- [ ] Cart functionality works

### AWS Deployment

- [ ] SAM build completes successfully
- [ ] SAM deploy completes without errors
- [ ] Lambda function created
- [ ] DynamoDB table created
- [ ] S3 bucket created
- [ ] Function URL accessible
- [ ] Health check works via Function URL
- [ ] Frontend deployed to S3
- [ ] Frontend accessible via S3 URL
- [ ] End-to-end chat flow works

## Troubleshooting Checklist

### Issue: Local server won't start

- [ ] Check Python version (must be 3.11+)
- [ ] Check dependencies installed: `pip list | grep fastapi`
- [ ] Check .env file exists: `ls -la .env`
- [ ] Check for port conflicts: `lsof -i :8000`

### Issue: OpenAI API errors

- [ ] Verify API key is correct: `grep OPENAI_API_KEY .env`
- [ ] Check API key has credits: https://platform.openai.com/usage
- [ ] Test API key directly:
  ```bash
  curl https://api.openai.com/v1/models \
    -H "Authorization: Bearer $OPENAI_API_KEY"
  ```

### Issue: UCP API errors

- [ ] Test UCP endpoint directly:
  ```bash
  curl https://n5je6mqzsskozc32cqdfetl42q0augte.lambda-url.us-east-1.on.aws/.well-known/ucp
  ```
- [ ] Check UCP_BASE_URL in .env or Lambda environment
- [ ] Verify UCP headers are included (check logs)

### Issue: SAM deploy fails

- [ ] Check AWS credentials: `aws sts get-caller-identity`
- [ ] Check region is set: `aws configure get region`
- [ ] Verify SAM CLI version: `sam --version`
- [ ] Check CloudFormation in AWS Console for error details

### Issue: Frontend can't connect to API

- [ ] Check CORS configuration in template.yaml
- [ ] Verify Function URL in browser console
- [ ] Check browser console for errors (F12)
- [ ] Test Function URL directly with curl
- [ ] Verify API returns valid JSON

### Issue: DynamoDB access denied

- [ ] Check Lambda IAM role has DynamoDB policy
- [ ] Verify table name matches environment variable
- [ ] Check table exists: `aws dynamodb describe-table --table-name ConversationSessions`

## Success Indicators

### Local Development Success
✅ Server starts without errors
✅ Can curl /health endpoint
✅ Frontend loads and displays chat interface
✅ Can send messages and receive responses
✅ Console shows no JavaScript errors

### AWS Deployment Success
✅ CloudFormation stack shows CREATE_COMPLETE
✅ Lambda function URL is accessible
✅ DynamoDB table exists and is empty
✅ S3 bucket hosts frontend files
✅ Can complete full conversation via web UI

## Next Steps After Setup

### 1. Test Complete Flow
- Search for products
- Add items to cart
- Apply discount code
- Complete order
- Verify order confirmation

### 2. Customize
- Add your own products to catalog
- Customize system prompt
- Style frontend to match your brand
- Add more discount codes

### 3. Monitor
- Check CloudWatch logs
- Monitor Lambda metrics
- Track DynamoDB usage
- Review OpenAI API usage

### 4. Secure (Production)
- Add authentication
- Move API key to Secrets Manager
- Enable WAF
- Add rate limiting

## Common Commands Reference

```bash
# Development
make dev              # Install dev dependencies
make local            # Start local server
make test             # Run tests
make format           # Format code
make lint             # Lint code

# Deployment
make build            # Build SAM app
make deploy           # Deploy to AWS
make deploy-frontend  # Deploy frontend to S3

# Utilities
make clean            # Clean build artifacts
make help             # Show help

# AWS
sam logs -n ChatbotFunction --tail        # View logs
sam local start-api                       # Run Lambda locally
aws dynamodb scan --table-name ConversationSessions  # View sessions
```

## Help & Support

### Documentation
- Quick Start: See QUICKSTART.md
- Full Guide: See README.md
- Architecture: See ARCHITECTURE.md
- Deployment: See DEPLOYMENT.md

### Debugging
- Check CloudWatch logs for Lambda
- Check browser console for frontend errors
- Use verbose logging: Set LOG_LEVEL=DEBUG in .env

### Common Issues
- OpenAI rate limits: Upgrade to paid tier
- Lambda timeout: Increase timeout in template.yaml
- CORS errors: Verify Function URL CORS config
- DynamoDB errors: Check IAM permissions

## Completion Status

When you can complete this flow, your setup is successful:

1. Open frontend URL
2. Type: "Show me roses"
3. See product cards displayed
4. Type: "Add red rose bouquet to cart"
5. See cart summary appear
6. Type: "Apply code 10OFF"
7. See discount applied
8. Type: "Complete order. John Doe, john@example.com, 123 Main St, Anytown CA 12345"
9. See order confirmation with order ID

**If all 9 steps work**: ✅ Setup Complete!
