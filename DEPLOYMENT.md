# Deployment Guide

This guide walks through deploying the Shopping Assistant Chatbot to AWS.

## Prerequisites

1. **AWS CLI** - Installed and configured with credentials
   ```bash
   aws configure
   ```

2. **AWS SAM CLI** - Install from https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
   ```bash
   # macOS
   brew install aws-sam-cli

   # Verify installation
   sam --version
   ```

3. **OpenAI API Key** - Get from https://platform.openai.com/api-keys

4. **Python 3.11+** - Required for local development and building

## Deployment Steps

### Step 1: Install Dependencies

```bash
# Install production dependencies
make install

# Or for development
make dev
```

### Step 2: Configure Environment (Local Testing)

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your OpenAI API key
nano .env
# Set: OPENAI_API_KEY=sk-your-actual-key-here
```

### Step 3: Test Locally (Optional but Recommended)

```bash
# Start local server
make local

# In another terminal, run tests
./test_local.sh
```

The local server will run at http://localhost:8000. Open `frontend/index.html` in a browser to test the chat interface.

### Step 4: Build SAM Application

```bash
make build

# This will:
# - Install dependencies in .aws-sam/build
# - Package the Lambda function
# - Prepare for deployment
```

### Step 5: Deploy to AWS

```bash
make deploy

# You'll be prompted for:
# - Stack Name: shopping-assistant-chatbot (or your choice)
# - AWS Region: us-east-1 (or your preferred region)
# - Parameter OpenAIApiKey: (paste your OpenAI API key - it will be hidden)
# - Confirm changes before deploy: Y
# - Allow SAM CLI IAM role creation: Y
# - Disable rollback: N
# - Save arguments to configuration file: Y
# - SAM configuration file: samconfig.toml
# - SAM configuration environment: default

# Deployment will take 2-5 minutes
```

### Step 6: Note the Outputs

After deployment, SAM will display outputs:

```
CloudFormation outputs from deployed stack
---------------------------------------------------------------------------
Outputs
---------------------------------------------------------------------------
Key                 ChatbotFunctionUrl
Description         Function URL for Chatbot API
Value               https://abc123.lambda-url.us-east-1.on.aws/

Key                 FrontendBucketUrl
Description         Website URL for Frontend
Value               http://shopping-assistant-frontend-123456789012.s3-website-us-east-1.amazonaws.com

Key                 DynamoDBTable
Description         DynamoDB Table Name
Value               ConversationSessions
---------------------------------------------------------------------------
```

**Important**: Save these URLs for the next step.

### Step 7: Deploy Frontend

The frontend needs to know the Lambda Function URL to make API calls.

**Option A: Auto-detect (Recommended)**

The frontend is already configured to auto-detect the API URL. Just deploy:

```bash
# Get bucket name from outputs (it will be shopping-assistant-frontend-YOUR_ACCOUNT_ID)
make deploy-frontend FRONTEND_BUCKET=shopping-assistant-frontend-YOUR_ACCOUNT_ID
```

**Option B: Configure explicitly**

If you want to set a specific API URL, edit `frontend/chat.js`:

```javascript
// Change this line:
const API_BASE_URL = window.location.origin.includes('localhost')
    ? 'http://localhost:8000'
    : 'https://your-lambda-url.lambda-url.us-east-1.on.aws';
```

Then deploy:

```bash
make deploy-frontend FRONTEND_BUCKET=shopping-assistant-frontend-YOUR_ACCOUNT_ID
```

### Step 8: Test the Deployment

1. **Open the Frontend URL** from the deployment outputs
2. **Start chatting**:
   - "Show me roses"
   - "Add the red rose bouquet to my cart"
   - "Add 2 ceramic pots"
   - "Apply code 10OFF"
   - "Complete my order. John Doe, john@example.com, 123 Main St, Anytown CA 12345"

3. **Verify in AWS Console**:
   - DynamoDB: Check ConversationSessions table for session data
   - CloudWatch: View Lambda logs for API calls
   - Lambda: Check function metrics

## Updating the Application

### Update Backend Code

```bash
# Make code changes in src/chatbot/

# Rebuild and deploy
make build
sam deploy
```

### Update Frontend

```bash
# Make changes in frontend/

# Redeploy to S3
make deploy-frontend FRONTEND_BUCKET=shopping-assistant-frontend-YOUR_ACCOUNT_ID
```

## Troubleshooting

### Issue: Lambda Function Timing Out

- Check CloudWatch logs: AWS Console → CloudWatch → Log Groups → /aws/lambda/shopping-assistant-chatbot
- Increase timeout in template.yaml under Globals.Function.Timeout
- Redeploy with `sam deploy`

### Issue: OpenAI API Errors

- Verify API key is correct in Lambda environment variables
- Check API key has sufficient credits at https://platform.openai.com/usage
- View errors in CloudWatch logs

### Issue: UCP API Errors

- Test UCP merchant API directly:
  ```bash
  curl https://n5je6mqzsskozc32cqdfetl42q0augte.lambda-url.us-east-1.on.aws/.well-known/ucp
  ```
- Check UCP_BASE_URL in Lambda environment variables
- Verify UCP headers are correctly formatted (check client.py)

### Issue: DynamoDB Access Denied

- Verify Lambda has DynamoDB permissions in template.yaml
- Check IAM role in AWS Console → Lambda → Configuration → Permissions
- Ensure table name matches environment variable

### Issue: Frontend Can't Connect to API

- Verify CORS is enabled on Lambda Function URL
- Check browser console for CORS errors
- Verify API_BASE_URL in frontend/chat.js
- Test API directly with curl

## Cleanup

To delete all AWS resources:

```bash
# Delete the CloudFormation stack
aws cloudformation delete-stack --stack-name shopping-assistant-chatbot

# Delete the frontend bucket (if not empty)
aws s3 rm s3://shopping-assistant-frontend-YOUR_ACCOUNT_ID --recursive
aws s3 rb s3://shopping-assistant-frontend-YOUR_ACCOUNT_ID
```

## Cost Estimates

### AWS Costs
- **Lambda**: ~$0.20 per million requests + $0.0000166667 per GB-second
- **DynamoDB**: Pay-per-request, ~$1.25 per million write requests
- **S3**: ~$0.023 per GB stored + $0.004 per 10,000 GET requests

### OpenAI Costs
- **GPT-3.5-turbo**: ~$0.0015 per 1K input tokens, ~$0.002 per 1K output tokens
- Average conversation: 5-10 messages = ~$0.01-0.05

**Estimated monthly cost for moderate usage (1000 conversations)**: $5-15

## Security Considerations

### Current Setup (MVP)
- Lambda Function URL with NO authentication (public)
- OpenAI API key stored in Lambda environment variables
- No user authentication

### Production Recommendations
1. Add authentication (API keys, JWT, AWS Cognito)
2. Store OpenAI API key in AWS Secrets Manager
3. Enable AWS WAF on API Gateway
4. Add rate limiting
5. Enable CloudTrail for audit logging
6. Use VPC for Lambda if accessing private resources
7. Enable encryption at rest for DynamoDB

## Monitoring

### CloudWatch Metrics
- Lambda invocations, errors, duration
- DynamoDB read/write capacity
- API Gateway requests (if using API Gateway)

### CloudWatch Logs
- Lambda function logs: `/aws/lambda/shopping-assistant-chatbot`
- Filter patterns:
  - Errors: `[time, request_id, level = ERROR*, ...]`
  - UCP calls: `"UCP"`
  - OpenAI calls: `"OpenAI"`

### Alarms (Recommended)
```bash
# Create CloudWatch alarm for Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name chatbot-errors \
  --alarm-description "Alert on Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=shopping-assistant-chatbot
```
