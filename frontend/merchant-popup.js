// Pure helpers for the merchant sign-in popup. No DOM access, so they can be
// unit tested in Node (see tests/frontend/merchant-popup.test.js).
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.MerchantPopup = factory();
    }
})(typeof self !== 'undefined' ? self : this, function () {
    var MESSAGE_TYPE = 'merchant-auth';
    var WINDOW_NAME = 'merchant-auth';

    // Where the popup page lives: the chatbot API, not the chat page.
    function senderOrigin(apiBaseUrl) {
        return new URL(apiBaseUrl).origin;
    }

    // window.open() feature string, centred over the opener and kept on screen.
    function popupFeatures(opener, width, height) {
        width = width || 520;
        height = height || 720;
        var outerW = opener.outerWidth || width;
        var outerH = opener.outerHeight || height;
        var left = Math.max(0, Math.round((opener.screenX || 0) + (outerW - width) / 2));
        var top = Math.max(0, Math.round((opener.screenY || 0) + (outerH - height) / 2));
        return 'popup=yes,width=' + width + ',height=' + height + ',left=' + left + ',top=' + top +
            ',resizable=yes,scrollbars=yes';
    }

    // Decide what a window message means. Returns null for anything that is not
    // a trustworthy merchant-auth result for this chat session.
    //   event:    the MessageEvent (origin, source, data)
    //   expected: { origin, source, sessionId }
    function interpretMessage(event, expected) {
        if (!event || event.origin !== expected.origin) return null;
        // Only the popup we opened may report a result
        if (!expected.source || event.source !== expected.source) return null;
        var data = event.data;
        if (!data || typeof data !== 'object' || data.type !== MESSAGE_TYPE) return null;
        if (data.status === 'success') {
            // A result for some other chat session is not ours to act on
            if (expected.sessionId && data.session_id && data.session_id !== expected.sessionId) return null;
            return { ok: true };
        }
        if (data.status === 'error') {
            return { ok: false, error: typeof data.error === 'string' ? data.error : 'unknown' };
        }
        return null;
    }

    var ERROR_TEXT = {
        invalid_state: 'The sign-in link was not valid. Please try connecting again.',
        session_not_found: 'I lost track of this chat session. Please refresh the page and try again.',
        missing_code_verifier: 'The sign-in link expired. Please try connecting again.',
        token_exchange_failed: 'The merchant did not accept the sign-in. Please try again.',
        unknown: 'Connecting to the merchant did not work. Please try again.'
    };

    function errorText(code) {
        return Object.prototype.hasOwnProperty.call(ERROR_TEXT, code) ? ERROR_TEXT[code] : ERROR_TEXT.unknown;
    }

    return {
        MESSAGE_TYPE: MESSAGE_TYPE,
        WINDOW_NAME: WINDOW_NAME,
        senderOrigin: senderOrigin,
        popupFeatures: popupFeatures,
        interpretMessage: interpretMessage,
        errorText: errorText
    };
});
