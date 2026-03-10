# Merchant Auth0 Issue - User Credentials

## Current Status

✅ Shopping assistant Auth0 login - **WORKING**
✅ Bot responds with authorization link - **WORKING**
✅ Redirects to merchant Auth0 - **WORKING**
❌ Merchant Auth0 login - **FAILING**

## The Error

```
Merchant Auth0 error: "Wrong email or password"
```

**Tenant**: agentic-commerce-merchant.cic-demo-platform.auth0app.com
**User**: play.write@atko.email
**Password**: Abcd!234

## Root Cause

The error "Wrong email or password" (not "bot detection") means:
- ✅ IP allowlist is working
- ❌ User doesn't exist in merchant Auth0 tenant OR password is wrong

## How to Fix

### Option 1: Verify User Exists in Merchant Auth0

1. Go to merchant Auth0 dashboard:
   - Tenant: **agentic-commerce-merchant.cic-demo-platform.auth0app.com**

2. Navigate to: **User Management → Users**

3. Search for: `play.write@atko.email`

4. If **NOT FOUND**:
   - Click **Create User**
   - Email: `play.write@atko.email`
   - Password: `Abcd!234`
   - Connection: Username-Password-Authentication (or your database)

5. If **FOUND**:
   - Click on the user
   - Go to **Settings**
   - Click **Set Password**
   - Set to: `Abcd!234`

### Option 2: Use Different Test User

If you want to use a different user that already exists in both Auth0 tenants:

1. Update `tests/e2e/.env`:
   ```bash
   TEST_USER_EMAIL=your-other-user@example.com
   TEST_USER_PASSWORD=YourPassword123
   ```

2. Make sure this user exists in BOTH:
   - grocery-b2c.cic-demo-platform.auth0app.com
   - agentic-commerce-merchant.cic-demo-platform.auth0app.com

### Option 3: Test Manually First

Before running the automated test, verify manually:

1. Open browser (private/incognito mode)
2. Go to: https://main.d7stwkdmkar4g.amplifyapp.com
3. Login with: `play.write@atko.email` / `Abcd!234`
4. Send message: "add roses to cart"
5. Click the authorization link
6. Try logging into merchant Auth0 with: `play.write@atko.email` / `Abcd!234`
7. If it works, run the test. If not, fix the user/password first.

## Verify & Run Test

Once fixed, run:
```bash
cd tests/e2e
npm test
```

Or watch it work:
```bash
npm run test:headed
```
