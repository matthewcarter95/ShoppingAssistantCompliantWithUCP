const { test, expect } = require('@playwright/test');

// This test allows you to manually complete the merchant Auth0 login
// Run with: npm run test:headed -- oauth-flow-manual-merchant-login.spec.js

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'play.write@atko.email';
const TEST_USER_PASSWORD = process.env.TEST_USER_PASSWORD;

if (!TEST_USER_PASSWORD) {
  throw new Error('TEST_USER_PASSWORD environment variable is required');
}

test('OAuth flow with manual merchant login', async ({ page }) => {
  console.log('Starting OAuth flow test with manual merchant login');

  // Steps 1-9: Automated
  console.log('Step 1-3: Login to shopping assistant');
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const loginButton = page.locator('#loginButton').first();
  await expect(loginButton).toBeVisible({ timeout: 10000 });
  await loginButton.click();

  await page.waitForURL(/grocery-b2c\.cic-demo-platform\.auth0app\.com/, { timeout: 15000 });

  const emailInput = page.locator('input[name="username"]').first();
  await emailInput.waitFor({ state: 'visible', timeout: 10000 });
  await emailInput.fill(TEST_USER_EMAIL);
  await emailInput.press('Enter');
  await page.waitForTimeout(1000);

  const passwordInput = page.locator('input[type="password"]').first();
  await passwordInput.waitFor({ state: 'visible', timeout: 10000 });
  await passwordInput.fill(TEST_USER_PASSWORD);

  await page.click('button[type="submit"], button[name="action"]');
  await page.waitForURL(/main\.d7stwkdmkar4g\.amplifyapp\.com/, { timeout: 15000 });
  await page.waitForLoadState('networkidle');

  console.log('✅ Shopping assistant login complete');

  // Step 8-9: Send message
  console.log('Step 8-9: Sending message to add roses to cart');
  const messageInput = page.locator('#messageInput, input[placeholder*="message"]');
  await expect(messageInput).toBeVisible({ timeout: 5000 });
  await messageInput.fill('add roses to cart');

  const sendButton = page.locator('#sendButton, button:has-text("Send")');
  await sendButton.click();

  // Wait for bot response
  await page.waitForTimeout(10000);
  console.log('✅ Bot response received');

  // Find and click authorization link
  const authLink = page.locator('a[href*="agentic-commerce-merchant"]').or(
    page.locator('button:has-text("Connect")').or(
      page.locator('a:has-text("authorize")')
    )
  );
  await authLink.waitFor({ state: 'visible', timeout: 10000 });
  await authLink.click();

  await page.waitForURL(/agentic-commerce-merchant\.cic-demo-platform\.auth0app\.com/, { timeout: 15000 });
  console.log('✅ Redirected to merchant Auth0');

  // PAUSE HERE FOR MANUAL LOGIN
  console.log('\n⏸️  PAUSED - Please complete the merchant Auth0 login manually in the browser window');
  console.log('   Email: play.write@atko.email');
  console.log('   Enter your password and click Submit');
  console.log('   The test will continue automatically after redirect...\n');

  // Wait for redirect back to app (with longer timeout for manual login)
  await page.waitForURL(/main\.d7stwkdmkar4g\.amplifyapp\.com/, { timeout: 120000 }); // 2 minutes
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);

  console.log('✅ Redirected back to chatbot after authorization');

  // Verify success
  console.log('Verifying authorization success...');
  await page.screenshot({ path: 'test-results/manual-after-auth.png', fullPage: true });

  // Try adding roses again
  console.log('Attempting to add roses to cart (should work now)...');
  await messageInput.fill('add roses to cart');
  await sendButton.click();

  await page.waitForTimeout(10000);
  await page.screenshot({ path: 'test-results/manual-final.png', fullPage: true });

  console.log('✅ Test complete! Check screenshots in test-results/');
});
