# OAuth Callback Architecture Change

## What Changed

We've improved the OAuth callback flow to be more reliable and follow standard OAuth patterns.

### Old Flow (Frontend-Handled Callback):
1. Merchant Auth0 redirects to: `https://main.d7stwkdmkar4g.amplifyapp.com/?code=...&state=...`
2. Frontend JavaScript detects callback
3. Frontend POSTs to backend `/webhooks/auth/callback`
4. Backend exchanges code for token

### New Flow (Backend-Handled Callback) ✅:
1. Merchant Auth0 redirects to: `https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws/webhooks/auth/callback?code=...&state=...`
2. Backend receives GET request with code and state
3. Backend exchanges code for token
4. Backend redirects back to: `https://main.d7stwkdmkar4g.amplifyapp.com/?merchant_auth=success`

## Benefits

✅ More reliable (no frontend JavaScript dependency)
✅ Standard OAuth pattern (backend handles callback)
✅ Better error handling (backend controls the flow)
✅ Cleaner separation of concerns

## Required Configuration Change

⚠️ **IMPORTANT**: You must update the merchant Auth0 application settings:

### Update Allowed Callback URLs

1. Go to merchant Auth0 dashboard: **agentic-commerce-merchant.cic-demo-platform.auth0app.com**
2. Navigate to: Applications → Applications
3. Find: Shopping assistant app (Client ID: `U5xtIqc7cu707C28nQHeCKplg9ec2VPe`)
4. Settings → Application URIs
5. Update **Allowed Callback URLs** to:
   ```
   https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws/webhooks/auth/callback
   ```
6. **Save Changes**

### Keep These URLs Too (Optional):

If you want to support both flows during transition, you can keep both URLs:
```
https://main.d7stwkdmkar4g.amplifyapp.com/,
https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws/webhooks/auth/callback
```

But the frontend callback handling code is now obsolete and can be removed.

## Frontend Changes

The frontend no longer needs to handle the OAuth callback. After the backend processes the callback and redirects back, the frontend simply needs to:

1. Check for `?merchant_auth=success` parameter
2. Show success message to user
3. User can continue shopping

The frontend callback handling code in `chat.js` (lines 48-69 and 341-420) is now obsolete.

## Testing

Once you've updated the Allowed Callback URLs in Auth0:

```bash
cd tests/e2e
npm test oauth-flow.spec.js
```

The test should now complete successfully! 🎉
