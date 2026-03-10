# E2E Test Status

## Test Setup: ✅ Complete

The Playwright test suite is fully set up and working correctly.

## Current Status: 🟡 Almost There!

### What's Working ✅

✅ Shopping assistant login (grocery-b2c Auth0)
✅ Sends "add roses to cart" message
✅ Receives bot response with authorization link
✅ Clicks authorization link
✅ Redirects to merchant Auth0
✅ Handles multi-step Auth0 login flow

### Current Issue: ❌ Merchant Auth0 Credentials

The merchant Auth0 login is failing with:
```
Merchant Auth0 error: "Wrong email or password"
```

**Tenant**: agentic-commerce-merchant.cic-demo-platform.auth0app.com
**Email**: `play.write@atko.email`
**Password**: `Abcd!234`

## Next Steps

### 1. Add IP to Merchant Auth0 Allowlist ⚠️

You've already added your IP to the shopping assistant Auth0. Now add it to:
- **Merchant Auth0**: agentic-commerce-merchant.cic-demo-platform.auth0app.com
- Go to Security → Attack Protection → Bot Detection
- Add your IP to the allowlist

### 2. Verify User Exists in Merchant Auth0

Ensure `play.write@atko.email` exists in the merchant Auth0 tenant:
- Go to User Management → Users
- Search for `play.write@atko.email`
- If not found, create the user with password `Abcd!234`
- If found, verify/reset password to `Abcd!234`

### 3. Test Manually (Optional)

To verify credentials work:
1. Go through the flow manually in browser
2. Add item to cart
3. Click the authorization link
4. Login with `play.write@atko.email` / `Abcd!234`
5. Should redirect back successfully

### 4. Run Test Again

Once the IP is allowlisted and user exists:
```bash
cd tests/e2e
npm test
```

## Test Coverage

Current progress through the flow:

1. ✅ Shopping assistant login (Auth0 #1)
2. ✅ Send "add roses to cart" message
3. ✅ Receive merchant authorization prompt with link
4. ✅ Click authorization link
5. ✅ Redirect to merchant Auth0
6. ❌ **Merchant Auth0 login (Auth0 #2)** ← Currently failing here
7. ⏳ Approve authorization (if needed)
8. ⏳ Redirect back with authorization code
9. ⏳ Backend exchanges code for tokens (PKCE)
10. ⏳ Verify merchant connection success message
11. ⏳ Add roses to cart successfully

## Debug Mode

To see what's happening in the browser:
```bash
npm run test:headed   # Watch the browser
npm run test:debug    # Step-by-step with Playwright Inspector
```

## Screenshots

Test captures screenshots at each step in `test-results/` directory:
- `01-landing.png` - Initial page load
- `02-auth0-login.png` - Auth0 login page
- `03-credentials-filled.png` - After filling credentials
- `04-after-submit.png` - After submitting login
- And more as the test progresses...
