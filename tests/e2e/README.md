# End-to-End Tests for Shopping Assistant

Automated Playwright tests for the complete OAuth flow including shopping assistant login and merchant authorization.

## Setup

1. Install dependencies:
```bash
cd tests/e2e
npm install
npx playwright install chromium
```

2. Set environment variables:
```bash
export TEST_USER_EMAIL="play.write@atko.email"
export TEST_USER_PASSWORD="your-password-here"
```

Or create a `.env` file:
```bash
cp .env.example .env
# Edit .env and add your password
```

## Running Tests

**Headless mode (default):**
```bash
npm test
```

**Headed mode (see browser):**
```bash
npm run test:headed
```

**Debug mode (step through with Playwright Inspector):**
```bash
npm run test:debug
```

**Watch mode:**
```bash
npx playwright test --ui
```

## Test Flow

The main test (`oauth-flow.spec.js`) performs the following steps:

1. ✅ Navigate to shopping assistant
2. ✅ Click Login button
3. ✅ Redirect to shopping assistant Auth0
4. ✅ Fill in credentials and submit
5. ✅ Redirect back to chatbot
6. ✅ Verify user is logged in
7. ✅ Send "add roses to cart" message
8. ✅ Wait for bot response with merchant authorization link
9. ✅ Click the authorization link
10. ✅ Redirect to merchant Auth0
11. ✅ Login to merchant Auth0 (if needed)
12. ✅ Approve authorization
13. ✅ Redirect back to chatbot
14. ✅ Verify success message appears
15. ✅ Verify user is still logged in
16. ✅ Try adding roses again (should work without re-auth)
17. ✅ Verify cart is updated

## Test Results

Test results are saved in:
- `test-results/` - Screenshots at each step
- `playwright-report/` - HTML report (open with `npx playwright show-report`)
- `test-results/videos/` - Video recordings (on failure)

## Viewing Test Results

```bash
# Open HTML report
npx playwright show-report

# View screenshots
open test-results/*.png
```

## Troubleshooting

**Test fails at Auth0 login:**
- Check that TEST_USER_PASSWORD is set correctly
- Verify the user exists in both Auth0 tenants
- Check Auth0 selector might have changed

**Test fails at merchant authorization:**
- Check that the user is approved in merchant Auth0
- Verify redirect URI is whitelisted in merchant Auth0

**"Element not found" errors:**
- Run with `--headed` to see what's happening
- Update selectors if UI has changed
- Check console logs in the terminal

## CI/CD Integration

To run in CI (GitHub Actions, etc):

```yaml
- name: Install Playwright
  run: |
    cd tests/e2e
    npm ci
    npx playwright install --with-deps chromium

- name: Run E2E tests
  env:
    TEST_USER_EMAIL: play.write@atko.email
    TEST_USER_PASSWORD: ${{ secrets.TEST_USER_PASSWORD }}
  run: |
    cd tests/e2e
    npm test
```
