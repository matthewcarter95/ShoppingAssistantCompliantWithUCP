// Pure helpers for the "approve access to your orders" step. No DOM access, so they can be
// unit tested in Node (see tests/frontend/pact-orders.test.js).
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.PactOrders = factory();
    }
})(typeof self !== 'undefined' ? self : this, function () {
    var WINDOW_NAME = 'pact-orders-auth';
    var MIN_INTERVAL_MS = 3000;
    var MAX_INTERVAL_MS = 30000;
    var MAX_WAIT_MS = 11 * 60 * 1000; // the device code lives 10 minutes; stop a little after

    // The link comes from the merchant's Provider, via our server. Open it only if it is plain https
    // (or http on localhost, for local development).
    function isSafeAuthUrl(url) {
        if (typeof url !== 'string') return false;
        var u;
        try { u = new URL(url); } catch (e) { return false; }
        if (u.username || u.password || !u.hostname) return false;
        if (u.protocol === 'https:') return true;
        return u.protocol === 'http:' && (u.hostname === 'localhost' || u.hostname === '127.0.0.1');
    }

    // How long to wait before asking the server again. The server tells us its interval (and
    // lengthens it after slow_down); never go faster than that or below the floor.
    function nextDelayMs(intervalSeconds) {
        var ms = (Number(intervalSeconds) || 5) * 1000;
        return Math.min(MAX_INTERVAL_MS, Math.max(MIN_INTERVAL_MS, ms));
    }

    // What to do with the server's answer to one poll.
    //   keep:    show nothing and poll again
    //   say:     show this text, and stop (or stop quietly if text is empty)
    function interpretResume(result) {
        if (!result || typeof result !== 'object') return { keep: false, say: 'Something went wrong checking on your approval. Please ask again.' };
        switch (result.status) {
            case 'pending':
                return { keep: true, delayMs: nextDelayMs(result.interval) };
            case 'reply':
            case 'denied':
            case 'expired':
            case 'error':
                return { keep: false, say: typeof result.text === 'string' ? result.text : '' };
            case 'step_up':
                // The merchant wants more than was approved; the server issued a fresh link.
                return { keep: false, again: true, say: typeof result.text === 'string' ? result.text : '', authUrl: result.auth_url };
            case 'none':
                return { keep: false, say: '' };
            default:
                return { keep: false, say: 'Something went wrong checking on your approval. Please ask again.' };
        }
    }

    // True while we should keep polling at all
    function withinWindow(startedAtMs, nowMs) {
        return nowMs - startedAtMs < MAX_WAIT_MS;
    }

    return {
        WINDOW_NAME: WINDOW_NAME,
        MIN_INTERVAL_MS: MIN_INTERVAL_MS,
        MAX_WAIT_MS: MAX_WAIT_MS,
        isSafeAuthUrl: isSafeAuthUrl,
        nextDelayMs: nextDelayMs,
        interpretResume: interpretResume,
        withinWindow: withinWindow
    };
});
