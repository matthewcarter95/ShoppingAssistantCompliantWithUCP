const { test, expect } = require('@playwright/test');

test('Verify no merchant auth banner appears after OAuth completes', async ({ page }) => {
    const APP_URL = 'https://main.d7stwkdmkar4g.amplifyapp.com/';
    const AUTH0_EMAIL = 'play.write@atko.email';
    const AUTH0_PASSWORD = 'Chatbot123!';
    const MERCHANT_EMAIL = 'matt.carter@atko.email';
    const MERCHANT_PASSWORD = 'Chatbot123!';

    console.log('\n🧪 Testing: No merchant auth banner after OAuth\n');

    // Navigate and login
    await page.goto(APP_URL);
    await page.waitForLoadState('networkidle');

    const loginButton = page.locator('#loginButton');
    await loginButton.click();

    await page.waitForURL(/grocery-b2c\.cic-demo-platform\.auth0app\.com/);

    const emailInput = page.locator('input[type="email"], input[name="username"]');
    await emailInput.fill(AUTH0_EMAIL);
    await emailInput.press('Enter');

    const passwordInput = page.locator('input[type="password"], input[name="password"]');
    await passwordInput.waitFor({ state: 'visible' });
    await passwordInput.fill(AUTH0_PASSWORD);
    await passwordInput.press('Enter');

    await page.waitForURL(APP_URL + '*');

    // Add roses to cart (triggers OAuth)
    const messageInput = page.locator('#messageInput, input[placeholder*="message"]');
    const sendButton = page.locator('#sendButton, button:has-text("Send")');

    await messageInput.fill('add roses to cart');
    await sendButton.click();

    await page.waitForTimeout(2000);

    // Click merchant auth link
    const authLink = page.locator('a.merchant-auth-link, a:has-text("authorize")').first();
    await authLink.click();

    await page.waitForURL(/agentic-commerce-merchant\.cic-demo-platform\.auth0app\.com/);

    // Login to merchant
    const merchantEmailInput = page.locator('input[type="email"], input[name="username"]');
    await merchantEmailInput.fill(MERCHANT_EMAIL);
    await merchantEmailInput.press('Enter');

    const merchantPasswordInput = page.locator('input[type="password"], input[name="password"]');
    await merchantPasswordInput.waitFor({ state: 'visible' });
    await merchantPasswordInput.fill(MERCHANT_PASSWORD);
    await merchantPasswordInput.press('Enter');

    // Wait for redirect back
    await page.waitForURL(APP_URL + '*', { timeout: 15000 });
    console.log('✅ Redirected back to chatbot after OAuth');

    // Wait for page to fully load
    await page.waitForTimeout(3000);

    // Add roses again
    const messageInput2 = page.locator('#messageInput, input[placeholder*="message"]');
    const sendButton2 = page.locator('#sendButton, button:has-text("Send")');
    await messageInput2.fill('add roses to cart');
    await sendButton2.click();

    // Wait for cart to update
    await page.waitForTimeout(5000);

    // Check for merchant auth banner
    const merchantBanner = page.locator('#merchantAuthPrompt, [id*="merchant"], [class*="merchant-auth"]');
    const bannerVisible = await merchantBanner.isVisible().catch(() => false);

    if (bannerVisible) {
        const bannerText = await merchantBanner.textContent();
        console.log('❌ FAIL: Merchant auth banner is still visible!');
        console.log('   Banner text:', bannerText);
        throw new Error('Merchant auth banner should not be visible after OAuth completes');
    } else {
        console.log('✅ PASS: No merchant auth banner visible');
    }

    // Also check button text
    const connectButton = page.locator('#connectMerchantButton, button:has-text("Connect")');
    const buttonVisible = await connectButton.isVisible().catch(() => false);

    if (buttonVisible) {
        console.log('⚠️  WARNING: Connect Merchant button is visible');
    } else {
        console.log('✅ Connect Merchant button is hidden');
    }

    console.log('\n✅ Test passed: No merchant auth banner after OAuth\n');
});
