// Run with: node --test tests/frontend/
const test = require('node:test');
const assert = require('node:assert');
const P = require('../../frontend/merchant-popup.js');

const API = 'https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws';
const popup = { id: 'popup' };
const expected = (over) => Object.assign({ origin: P.senderOrigin(API), source: popup, sessionId: 's1' }, over);
const msg = (over) => Object.assign(
    { origin: P.senderOrigin(API), source: popup, data: { type: 'merchant-auth', status: 'success', session_id: 's1' } }, over);

test('sender origin is the API origin, with no path', () => {
    assert.strictEqual(P.senderOrigin(API + '/some/path'), API);
});

test('a success from our popup, from the API origin, for this session is accepted', () => {
    assert.deepStrictEqual(P.interpretMessage(msg(), expected()), { ok: true });
});

test('a message from another origin is ignored', () => {
    assert.strictEqual(P.interpretMessage(msg({ origin: 'https://evil.example' }), expected()), null);
});

test('a message from a window that is not our popup is ignored, even from the right origin', () => {
    assert.strictEqual(P.interpretMessage(msg({ source: { id: 'other' } }), expected()), null);
});

test('with no popup open nothing is accepted', () => {
    assert.strictEqual(P.interpretMessage(msg({ source: null }), expected({ source: null })), null);
});

test('a result for a different chat session is ignored', () => {
    const wrong = msg({ data: { type: 'merchant-auth', status: 'success', session_id: 'someone-else' } });
    assert.strictEqual(P.interpretMessage(wrong, expected()), null);
});

test('unrelated messages (other libraries, other types, junk) are ignored', () => {
    for (const data of [null, undefined, 'merchant-auth', 42, {}, { type: 'other', status: 'success' },
                        { type: 'merchant-auth' }, { type: 'merchant-auth', status: 'maybe' }]) {
        assert.strictEqual(P.interpretMessage(msg({ data }), expected()), null, JSON.stringify(data));
    }
});

test('an error result is reported with its code', () => {
    const err = msg({ data: { type: 'merchant-auth', status: 'error', error: 'token_exchange_failed' } });
    assert.deepStrictEqual(P.interpretMessage(err, expected()), { ok: false, error: 'token_exchange_failed' });
});

test('an error with a non-string code becomes unknown', () => {
    const err = msg({ data: { type: 'merchant-auth', status: 'error', error: { x: 1 } } });
    assert.deepStrictEqual(P.interpretMessage(err, expected()), { ok: false, error: 'unknown' });
});

test('error text is fixed for known codes and generic for anything else', () => {
    assert.match(P.errorText('invalid_state'), /not valid/);
    assert.strictEqual(P.errorText('nonsense'), P.errorText('unknown'));
    assert.strictEqual(P.errorText('__proto__'), P.errorText('unknown'));
    assert.strictEqual(P.errorText('toString'), P.errorText('unknown'));
});

test('popup features centre the window over the opener and stay on screen', () => {
    const f = P.popupFeatures({ outerWidth: 1400, outerHeight: 900, screenX: 100, screenY: 50 });
    assert.match(f, /width=520/); assert.match(f, /height=720/);
    assert.match(f, /left=540/); assert.match(f, /top=140/);
    const off = P.popupFeatures({ outerWidth: 300, outerHeight: 300, screenX: -500, screenY: -500 });
    assert.match(off, /left=0/); assert.match(off, /top=0/);
});
