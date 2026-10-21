// Run with: node --test tests/frontend/
const test = require('node:test');
const assert = require('node:assert');
const P = require('../../frontend/pact-orders.js');

test('only plain https links are opened', () => {
    assert.strictEqual(P.isSafeAuthUrl('https://smitty-api.demo-connect.us/pact/login?return_to=x'), true);
    for (const bad of ['http://shop.example/login', 'javascript:alert(1)', 'data:text/html,x', 'https://u:p@shop.example/',
        '//shop.example/x', 'not a url', '', null, undefined, 42, {}]) {
        assert.strictEqual(P.isSafeAuthUrl(bad), false, String(bad));
    }
});

test('http is allowed only on localhost, for local development', () => {
    assert.strictEqual(P.isSafeAuthUrl('http://localhost:3000/login'), true);
    assert.strictEqual(P.isSafeAuthUrl('http://127.0.0.1:3000/login'), true);
    assert.strictEqual(P.isSafeAuthUrl('http://localhost.evil.example/login'), false);
});

test('the delay follows the server interval, within a floor and a ceiling', () => {
    assert.strictEqual(P.nextDelayMs(5), 5000);
    assert.strictEqual(P.nextDelayMs(10), 10000);
    assert.strictEqual(P.nextDelayMs(1), P.MIN_INTERVAL_MS);
    assert.strictEqual(P.nextDelayMs(600), 30000);
    assert.strictEqual(P.nextDelayMs(undefined), 5000);
    assert.strictEqual(P.nextDelayMs('abc'), 5000);
});

test('pending means keep polling at the server\'s pace, including after slow_down', () => {
    assert.deepStrictEqual(P.interpretResume({ status: 'pending', interval: 5 }), { keep: true, delayMs: 5000 });
    assert.deepStrictEqual(P.interpretResume({ status: 'pending', interval: 10 }), { keep: true, delayMs: 10000 });
});

test('a reply, denial, expiry or error stops polling and says the server\'s words', () => {
    for (const status of ['reply', 'denied', 'expired', 'error']) {
        assert.deepStrictEqual(P.interpretResume({ status, text: 'hello' }), { keep: false, say: 'hello' });
    }
});

test('a step-up during resume stops polling and carries the fresh link', () => {
    const r = P.interpretResume({ status: 'step_up', text: 'more please', auth_url: 'https://shop.example/login' });
    assert.deepStrictEqual(r, { keep: false, again: true, say: 'more please', authUrl: 'https://shop.example/login' });
});

test('"none" ends quietly; unknown or malformed answers end with an apology, never a hang', () => {
    assert.deepStrictEqual(P.interpretResume({ status: 'none' }), { keep: false, say: '' });
    for (const odd of [null, undefined, 'x', 7, {}, { status: 'who-knows' }]) {
        const r = P.interpretResume(odd);
        assert.strictEqual(r.keep, false);
        assert.match(r.say, /Something went wrong/);
    }
});

test('a non-string text never reaches the page as anything but an empty string', () => {
    assert.strictEqual(P.interpretResume({ status: 'reply', text: { html: '<b>' } }).say, '');
});

test('polling gives up a little after the device code would have expired', () => {
    assert.strictEqual(P.withinWindow(0, 5 * 60 * 1000), true);
    assert.strictEqual(P.withinWindow(0, P.MAX_WAIT_MS), false);
});
