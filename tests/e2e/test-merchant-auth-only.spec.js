const { test, expect } = require('@playwright/test');

// Simplified test to verify merchant Auth0 login works
const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'play.write@atko.email';
const TEST_USER_PASSWORD = process.env.TEST_USER_PASSWORD;

if (!TEST_USER_PASSWORD) {
  throw new Error('TEST_USER_PASSWORD environment variable is required');
}

test('Test merchant Auth0 login directly', async ({ page }) => {
  console.log('Testing merchant Auth0 login with:', TEST_USER_EMAIL);

  // Go directly to merchant Auth0 with a test authorization request
  // This simulates what happens when the user clicks "authorize"
  const merchantAuthUrl = 'https://agentic-commerce-merchant.cic-demo-platform.auth0app.com/authorize';
  const params = new URLSearchParams({
    client_id: 'U5xtIqc7cu707C28nQHeCKplg9ec2VPe', // Shopping assistant's client ID
    response_type: 'code',
    redirect_uri: 'https://main.d7stwkdmkar4g.amplifyapp.com/auth/callback',
    scope: 'openid profile email ucp:scopes:checkout_session',
    audience: 'api://ucp.session.service',
    state: 'test_state_123',
    code_challenge: 'test_challenge',
    code_challenge_method: 'S256'
  });

  await page.goto(`${merchantAuthUrl}?${params.toString()}`);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: 'test-results/merchant-01-login-page.png', fullPage: true });

  console.log('Current URL:', page.url());

  // Fill in credentials
  console.log('Filling email...');
  const emailInput = page.locator('input[name="username"]').first();
  await emailInput.waitFor({ state: 'visible', timeout: 10000 });
  await emailInput.fill(TEST_USER_EMAIL);
  await emailInput.press('Enter');

  console.log('Waiting for password field...');
  await page.waitForTimeout(1500);

  const passwordInput = page.locator('input[type="password"]').first();
  await passwordInput.waitFor({ state: 'visible', timeout: 10000 });

  console.log('Filling password...');
  await passwordInput.fill(TEST_USER_PASSWORD);
  await page.screenshot({ path: 'test-results/merchant-02-credentials-filled.png', fullPage: true });

  console.log('Submitting login...');
  await page.click('button[type="submit"], button[name="action"]');
  await page.waitForTimeout(3000);

  // Check result
  const currentUrl = page.url();
  console.log('URL after submit:', currentUrl);
  await page.screenshot({ path: 'test-results/merchant-03-after-submit.png', fullPage: true });

  // Check for errors
  const errorSelectors = [
    '.ulp-input-error-message',
    '[role="alert"]',
    '.error-message'
  ];

  let foundError = false;
  for (const selector of errorSelectors) {
    const errorEl = page.locator(selector);
    const hasError = await errorEl.isVisible({ timeout: 500 }).catch(() => false);
    if (hasError) {
      const errorText = await errorEl.textContent();
      console.log(`❌ Error found (${selector}):`, errorText?.trim());
      foundError = true;
      break;
    }
  }

  if (!foundError) {
    console.log('✅ No error message found - login might have succeeded!');
    console.log('Final URL:', currentUrl);

    // Check if we're redirected to callback or approval page
    if (currentUrl.includes('auth/callback') || currentUrl.includes('main.d7stwkdmkar4g')) {
      console.log('✅ Successfully redirected to callback!');
    } else if (currentUrl.includes('/authorize') || currentUrl.includes('consent')) {
      console.log('✅ Reached authorization/consent page!');
    }
  }

  // Take final screenshot
  await page.screenshot({ path: 'test-results/merchant-04-final.png', fullPage: true });
});
