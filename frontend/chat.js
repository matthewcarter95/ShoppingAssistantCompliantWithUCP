// ===== Configuration =====
// Auth0 Configuration (public client-side values)
const AUTH0_DOMAIN = 'grocery-b2c.cic-demo-platform.auth0app.com';
const AUTH0_CLIENT_ID = '1vykALbEbAw4ltcrTMDnnRasNllHluqK';

// API endpoint configuration
const API_BASE_URL = window.location.protocol === 'file:' || window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws';

// ===== Global State =====
let auth0Client = null;
let currentUser = null;
let accessToken = null;
let sessionId = null;
let merchantAuthInitiated = false;
let merchantAuthJustCompleted = false;
let merchantPopup = null;          // the sign-in popup window, while it is open
let merchantPopupWatcher = null;   // interval that notices the popup being closed
let pactPopup = null;              // the merchant's "allow access to your orders" window
let pactPoll = null;               // timer that asks our server whether the shopper has approved
let pactWatcher = null;            // notices the shopper closing that window
let pactWaitingSince = 0;

// ===== DOM Elements =====
const chatContainer = document.getElementById('chatContainer');
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const cartSummary = document.getElementById('cartSummary');
const cartItems = document.getElementById('cartItems');
const cartTotal = document.getElementById('cartTotal');
const inputContainer = document.getElementById('inputContainer');

// Auth UI elements
const authLoading = document.getElementById('authLoading');
const authButtons = document.getElementById('authButtons');
const loginButton = document.getElementById('loginButton');
const logoutButton = document.getElementById('logoutButton');
const userProfile = document.getElementById('userProfile');
const userAvatar = document.getElementById('userAvatar');
const userEmail = document.getElementById('userEmail');
const loginPrompt = document.getElementById('loginPrompt');
const loginPromptButton = document.getElementById('loginPromptButton');

// Merchant auth elements
const merchantAuthPrompt = document.getElementById('merchantAuthPrompt');
const connectMerchantButton = document.getElementById('connectMerchantButton');

// ===== Auth0 Initialization =====
async function initAuth0() {
    try {
        authLoading.style.display = 'block';

        // Check for merchant OAuth success redirect (from backend after processing callback)
        // IMPORTANT: Clean up URL BEFORE creating Auth0 client to prevent Auth0 from
        // trying to process merchant callback params as Auth0 OAuth params
        const query = window.location.search;
        const params = new URLSearchParams(query);

        if (params.get('merchant_auth') === 'success') {
            console.log('Detected merchant OAuth success redirect from backend');
            const sessionIdParam = params.get('session_id');

            // Restore session ID if provided
            if (sessionIdParam && !sessionId) {
                sessionId = sessionIdParam;
                localStorage.setItem('sessionId', sessionId);
            }

            // Set flags to show success message and skip status checks
            merchantAuthJustCompleted = true;

            // Store timestamp in sessionStorage so it persists across page reloads
            sessionStorage.setItem('merchantAuthCompletedAt', Date.now().toString());

            // Reset the merchantAuthInitiated flag since OAuth completed
            merchantAuthInitiated = false;

            // IMPORTANT: Hide the merchant auth banner permanently after OAuth completes
            // Once the user has authorized once, they don't need to see the banner again
            // The inline "authorize" buttons in chat messages are sufficient for re-auth if needed
            if (merchantAuthPrompt) {
                merchantAuthPrompt.style.display = 'none';
                console.log('Hiding merchant auth banner permanently after successful OAuth');
            }

            // Store flag in localStorage so banner never shows again for this user
            localStorage.setItem('merchantAuthCompleted', 'true');

            // Clean up URL BEFORE creating Auth0 client
            window.history.replaceState({}, document.title, window.location.pathname);
        }

        auth0Client = await window.auth0.createAuth0Client({
            domain: AUTH0_DOMAIN,
            clientId: AUTH0_CLIENT_ID,
            authorizationParams: {
                redirect_uri: window.location.origin,
                scope: 'openid profile email'
            },
            // Use ID token for user info since we don't have a custom API
            useRefreshTokens: true,
            cacheLocation: 'localstorage'
        });

        // Check if returning from shopping assistant Auth0 login redirect
        // Re-read query after potential URL cleanup
        const currentQuery = window.location.search;
        if (currentQuery.includes('code=') && currentQuery.includes('state=')) {
            await handleAuthCallback();
        }

        // Check if user is authenticated
        const isAuthenticated = await auth0Client.isAuthenticated();

        authLoading.style.display = 'none';
        authButtons.style.display = 'block';

        if (isAuthenticated) {
            await handleAuthenticated();
        } else {
            // Allow anonymous browsing
            setupAnonymousMode();
        }

    } catch (error) {
        console.error('Auth0 initialization error:', error);
        authLoading.style.display = 'none';
        showLoginPrompt();
    }
}

// ===== Auth Callback Handler =====
async function handleAuthCallback() {
    try {
        const query = window.location.search;
        const params = new URLSearchParams(query);
        const code = params.get('code');
        const state = params.get('state');

        // Check if this is a merchant auth callback
        // State format: {session_id}_{csrf_token}_{intent}
        if (code && state && state.includes('_')) {
            // Try to extract session ID from state parameter
            const stateParts = state.split('_');
            if (stateParts.length >= 3) {
                const stateSessionId = stateParts[0];
                const intent = stateParts[2];

                // Load session ID from localStorage if not already set
                if (!sessionId) {
                    sessionId = localStorage.getItem('sessionId');
                }

                // This is a merchant OAuth callback if state contains session ID with underscores
                if (stateSessionId && intent) {
                    console.log('Detected merchant OAuth callback');
                    await handleMerchantAuthCallback(code, state);
                    return;
                }
            }
        }

        // This is a shopping assistant login callback
        await auth0Client.handleRedirectCallback();

        // Clean up URL
        window.history.replaceState({}, document.title, window.location.pathname);

    } catch (error) {
        console.error('Auth callback error:', error);
        window.history.replaceState({}, document.title, window.location.pathname);
    }
}

// ===== Authenticated State =====
async function handleAuthenticated() {
    try {
        currentUser = await auth0Client.getUser();

        // Get ID token (contains email claim) instead of access token
        // Since we don't have a custom API, use the ID token for authentication
        try {
            const claims = await auth0Client.getIdTokenClaims();
            accessToken = claims.__raw; // This is the ID token JWT
            console.log('Using ID token for authentication');
        } catch (tokenError) {
            console.error('Failed to get ID token:', tokenError);
            // If token retrieval fails, try to re-authenticate
            await auth0Client.loginWithRedirect();
            return;
        }

        // Update UI
        userEmail.textContent = currentUser.email;
        userAvatar.src = currentUser.picture || 'https://via.placeholder.com/32';
        userProfile.style.display = 'flex';
        loginButton.style.display = 'none';
        hideLoginPrompt();
        chatMessages.style.display = 'block';
        inputContainer.style.display = 'flex';

        // Initialize session
        try {
            await initSession();
        } catch (sessionError) {
            console.error('Failed to initialize session:', sessionError);
            // Show error but don't block the UI
            addMessage('assistant', 'Welcome! There was an issue loading your session, but you can still chat with me.');
        }

        // Show appropriate message
        if (merchantAuthJustCompleted) {
            // Merchant auth just completed
            console.log('Handling merchant auth completion in handleAuthenticated');
            hideMerchantAuthPrompt();
            console.log('Merchant auth banner hidden');
            addMessage('assistant', 'Merchant account connected. I can now see your loyalty points. Ask me to add something to your cart whenever you are ready.');
            merchantAuthJustCompleted = false;
        } else if (!chatMessages.querySelector('.message')) {
            // First login
            addMessage('assistant', `Welcome back, ${currentUser.email}! How can I help you today?`);
        }

        messageInput.focus();

    } catch (error) {
        console.error('Error handling authenticated state:', error);
        showLoginPrompt();
    }
}

// ===== Login/Logout =====
async function login() {
    await auth0Client.loginWithRedirect({
        authorizationParams: {
            redirect_uri: window.location.origin
        }
    });
}

async function logout() {
    await auth0Client.logout({
        logoutParams: {
            returnTo: window.location.origin
        }
    });
    // Clear local state
    sessionId = null;
    localStorage.removeItem('sessionId');
}

function showLoginPrompt() {
    loginPrompt.style.display = 'flex';
    loginButton.style.display = 'block';
    // Don't hide chat interface - just show login prompt overlay
}

function hideLoginPrompt() {
    loginPrompt.style.display = 'none';
}

function setupAnonymousMode() {
    // Show chat interface for anonymous users
    chatMessages.style.display = 'block';
    inputContainer.style.display = 'flex';
    loginButton.style.display = 'block';
    userProfile.style.display = 'none';
    loginPrompt.style.display = 'none';

    // Generate anonymous session ID
    sessionId = localStorage.getItem('sessionId');
    if (!sessionId) {
        sessionId = generateUUID();
        localStorage.setItem('sessionId', sessionId);
    }

    // Add welcome message
    addMessage('assistant', 'Welcome! You can browse products anonymously. Login when you\'re ready to add items to your cart.');

    messageInput.focus();
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// ===== Session Management =====
async function initSession() {
    // Check for existing session in localStorage
    const existingSessionId = localStorage.getItem('sessionId');

    if (existingSessionId) {
        // Verify the session exists in the backend
        try {
            console.log(`Verifying existing session: ${existingSessionId}`);
            const response = await fetch(`${API_BASE_URL}/session/${existingSessionId}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                }
            });

            console.log(`Session verification response: ${response.status}`);

            if (response.ok) {
                sessionId = existingSessionId;
                console.log('Using existing session:', sessionId);
                return;
            } else {
                const errorText = await response.text();
                console.log(`Existing session not valid (${response.status}): ${errorText}`);
                localStorage.removeItem('sessionId');
            }
        } catch (error) {
            console.warn('Failed to verify existing session:', error);
            localStorage.removeItem('sessionId');
        }
    }

    // Create authenticated session
    try {
        const response = await fetch(`${API_BASE_URL}/session/new`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({})
        });

        if (!response.ok) {
            throw new Error(`Failed to create session: ${response.status}`);
        }

        const data = await response.json();
        sessionId = data.session_id;
        localStorage.setItem('sessionId', sessionId);
        console.log('Created new authenticated session:', sessionId);

    } catch (error) {
        console.error('Failed to create session:', error);
        // Fall back to anonymous session
        sessionId = generateUUID();
        localStorage.setItem('sessionId', sessionId);
    }
}

// ===== Merchant OAuth Flow =====
async function checkMerchantAuth() {
    if (!sessionId || merchantAuthInitiated) return true;

    // If merchant auth just completed (within last 10 seconds), trust that it worked
    // Don't check immediately to avoid race conditions with the ongoing chat request
    const merchantAuthCompletedAt = sessionStorage.getItem('merchantAuthCompletedAt');
    if (merchantAuthCompletedAt) {
        const elapsed = Date.now() - parseInt(merchantAuthCompletedAt);
        if (elapsed < 10000) {
            console.log(`Merchant auth just completed ${elapsed}ms ago, skipping status check to avoid race condition`);
            return true;
        } else {
            // Clear the timestamp after 10 seconds
            console.log(`Merchant auth completed ${elapsed}ms ago, clearing timestamp`);
            sessionStorage.removeItem('merchantAuthCompletedAt');
        }
    }

    try {
        console.log(`Checking merchant auth for session: ${sessionId}`);
        const response = await fetch(
            `${API_BASE_URL}/webhooks/auth/status?session_id=${sessionId}`,
            {
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                }
            }
        );

        console.log(`Merchant auth check response: ${response.status}`);

        if (!response.ok) {
            console.log(`Merchant auth check failed: ${response.status} ${response.statusText}`);
            return false;
        }

        const data = await response.json();
        console.log(`Merchant auth status: authorized=${data.authorized}`);
        return data.authorized;

    } catch (error) {
        console.error('Error checking merchant auth:', error);
        return false;
    }
}

// Open a blank popup for the merchant sign-in. Must run synchronously inside a
// click, or browsers block it; the sign-in address is filled in afterwards.
// Returns the window, or null if the browser blocked it.
function openMerchantPopup() {
    if (merchantPopup && !merchantPopup.closed) {
        merchantPopup.focus();
        return merchantPopup;
    }
    merchantPopup = window.open('about:blank', MerchantPopup.WINDOW_NAME, MerchantPopup.popupFeatures(window));
    if (!merchantPopup) return null;
    merchantAuthInitiated = true;
    watchMerchantPopup();
    return merchantPopup;
}

// Ask the server whether the merchant account is connected for this session
async function merchantIsAuthorized() {
    try {
        const response = await fetch(`${API_BASE_URL}/webhooks/auth/status?session_id=${sessionId}`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        if (!response.ok) return false;
        return (await response.json()).authorized === true;
    } catch (error) {
        return false;
    }
}

// When the popup closes without having told us the result, the server is the
// source of truth: the sign-in may have worked and only the message been lost
// (some identity providers cut the link between popup and opener).
function watchMerchantPopup() {
    clearInterval(merchantPopupWatcher);
    merchantPopupWatcher = setInterval(async () => {
        if (!merchantPopup || !merchantPopup.closed) return;
        clearInterval(merchantPopupWatcher);
        merchantPopup = null;
        if (!merchantAuthInitiated) return;
        merchantAuthInitiated = false;
        if (await merchantIsAuthorized()) {
            await onMerchantConnected();
        } else {
            addMessage('assistant', 'The merchant sign-in window was closed before it finished. Say the word and I will open it again.');
        }
    }, 600);
}

// The popup reports how it went. Only our own popup, from the API's origin, counts.
window.addEventListener('message', async (event) => {
    const result = MerchantPopup.interpretMessage(event, {
        origin: MerchantPopup.senderOrigin(API_BASE_URL),
        source: merchantPopup,
        sessionId: sessionId
    });
    if (!result) return;

    clearInterval(merchantPopupWatcher);
    merchantPopup = null;
    merchantAuthInitiated = false;

    if (!result.ok) {
        addMessage('assistant', MerchantPopup.errorText(result.error));
        return;
    }
    await onMerchantConnected();
});

// Merchant connected: carry on in this same page, with the chat as it was
async function onMerchantConnected() {
    // Keep the "just connected" window the status check relies on, and remember it
    sessionStorage.setItem('merchantAuthCompletedAt', Date.now().toString());
    localStorage.setItem('merchantAuthCompleted', 'true');
    hideMerchantAuthPrompt();

    // The invitation buttons already in the chat are now stale; retire them
    document.querySelectorAll('.merchant-connect-invite').forEach((el) => {
        el.classList.add('merchant-connect-done');
        const link = el.querySelector('.merchant-connect-button');
        if (link) link.remove();
    });

    addMessage('assistant', 'Merchant account connected. I can now see your loyalty points. Ask me to add something to your cart whenever you are ready.');
    messageInput.focus();
}

// Start the merchant sign-in in a popup. Always asks the server for a fresh
// sign-in link: links embedded in older chat messages carry a PKCE verifier
// that a newer link may since have replaced.
// `fallbackUrl` (optional) is used as a full-page redirect if popups are blocked.
async function initiateMerchantAuth(fallbackUrl) {
    if (merchantAuthInitiated) {
        console.log('Merchant auth already initiated, skipping');
        if (merchantPopup && !merchantPopup.closed) merchantPopup.focus();
        return;
    }

    // Open the popup right now, inside the click, then fill in its address
    const popup = openMerchantPopup();
    if (!popup) {
        if (typeof fallbackUrl === 'string' && fallbackUrl) {
            console.warn('Popup blocked, falling back to a full-page redirect');
            window.location.href = fallbackUrl;
            return;
        }
        addMessage('assistant', 'Your browser blocked the sign-in window. Please allow popups for this site and try again.');
        return;
    }

    console.log(`Initiating merchant auth for session: ${sessionId}`);

    try {
        const response = await fetch(
            `${API_BASE_URL}/webhooks/auth/create?session_id=${sessionId}`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                },
                body: JSON.stringify({
                    intent: 'create'
                })
            }
        );

        console.log(`Merchant auth create response: ${response.status}`);

        if (!response.ok) {
            const errorText = await response.text();
            console.error(`Failed to create merchant authorization: ${response.status} - ${errorText}`);
            throw new Error(`Failed to create merchant authorization: ${response.status}`);
        }

        const data = await response.json();
        console.log('Merchant auth created successfully, redirecting to authorization URL');

        // The server keeps the PKCE verifier with the session, because the
        // popup that handles the callback cannot read this page's storage
        popup.location.href = data.authorization_url;

    } catch (error) {
        console.error('Error initiating merchant auth:', error);
        try { popup.close(); } catch (e) { /* already gone */ }
        clearInterval(merchantPopupWatcher);
        merchantPopup = null;
        addMessage('assistant', 'Failed to initiate merchant authorization. Please try again.');
        merchantAuthInitiated = false;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

function addMerchantConnectInvite(promptText, authUrl) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content merchant-connect-invite';

    const explanation = document.createElement('p');
    explanation.textContent = promptText;

    const button = document.createElement('a');
    button.className = 'merchant-auth-link merchant-connect-button';
    button.href = authUrl;   // still a real link: middle-click or a blocked popup falls back to it
    button.textContent = 'Connect to merchant';
    button.addEventListener('click', (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        initiateMerchantAuth(authUrl);
    });

    contentDiv.appendChild(explanation);
    contentDiv.appendChild(button);
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// ===== Merchant order lookup: approval =====
// The merchant's agent will not show order details until the shopper approves access on the
// merchant's own site. We open that page in a popup (we never see the sign-in), then ask our
// server every few seconds whether it has been approved. The answer arrives as a chat message.
function addPactApproval(authUrl) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content pact-approval';

    const button = document.createElement('a');
    button.className = 'merchant-auth-link pact-approval-button';
    button.textContent = 'Review and approve';
    button.rel = 'noopener';
    button.target = '_blank';
    if (PactOrders.isSafeAuthUrl(authUrl)) {
        button.href = authUrl;   // still a real link: middle-click or a blocked popup falls back to it
        button.addEventListener('click', (e) => {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
            e.preventDefault();
            openPactApproval(authUrl, button);
        });
    } else {
        button.removeAttribute('href');
        button.textContent = 'Approval link unavailable';
    }

    contentDiv.appendChild(button);
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function stopPactPolling() {
    clearTimeout(pactPoll);
    clearInterval(pactWatcher);
    pactPoll = null;
    pactWatcher = null;
}

function retirePactButtons() {
    document.querySelectorAll('.pact-approval-button').forEach((el) => el.remove());
}

function openPactApproval(authUrl, button) {
    if (!PactOrders.isSafeAuthUrl(authUrl)) return;
    // Open inside the click so the browser allows it, to the merchant's own page
    const popup = window.open(authUrl, PactOrders.WINDOW_NAME, MerchantPopup.popupFeatures(window));
    if (!popup) {
        addMessage('assistant', 'Your browser blocked the approval window. Please allow popups for this site, then use the button again.');
        return;
    }
    pactPopup = popup;
    pactWaitingSince = Date.now();
    button.textContent = 'Waiting for your approval…';
    button.removeAttribute('href');
    startPactPolling();
}

function startPactPolling(delayMs) {
    stopPactPolling();
    // If the shopper closes the window, check once more: they may have approved just before closing.
    pactWatcher = setInterval(() => {
        if (pactPopup && pactPopup.closed) {
            clearInterval(pactWatcher);
            pactWatcher = null;
            pactPopup = null;
            pollPactOnce(true);
        }
    }, 700);
    pactPoll = setTimeout(() => pollPactOnce(false), delayMs || 4000);
}

async function pollPactOnce(lastChance) {
    if (!sessionId || !accessToken) { stopPactPolling(); return; }
    if (!PactOrders.withinWindow(pactWaitingSince, Date.now())) {
        stopPactPolling();
        retirePactButtons();
        addMessage('assistant', 'The approval request timed out. Ask me again and I will start a new one.');
        return;
    }
    let result;
    try {
        const response = await fetch(`${API_BASE_URL}/pact/orders/resume?session_id=${encodeURIComponent(sessionId)}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        result = await response.json();
    } catch (error) {
        console.error('Checking on the approval failed:', error);
        if (lastChance) { retirePactButtons(); addMessage('assistant', 'I could not check on your approval. Please ask again.'); return; }
        pactPoll = setTimeout(() => pollPactOnce(false), PactOrders.nextDelayMs(5));   // a blip: try again
        return;
    }

    const next = PactOrders.interpretResume(result);
    if (next.keep) {
        // If the window was closed without approval there is nothing more to wait for
        if (lastChance) {
            stopPactPolling();
            retirePactButtons();
            addMessage('assistant', 'The approval window was closed before it finished. Ask me again and I will reopen it.');
            return;
        }
        pactPoll = setTimeout(() => pollPactOnce(false), next.delayMs);
        return;
    }

    stopPactPolling();
    retirePactButtons();
    if (pactPopup && !pactPopup.closed) { try { pactPopup.close(); } catch (e) { /* already gone */ } }
    pactPopup = null;
    if (next.say) addMessage('assistant', next.say);
    if (next.again && next.authUrl) addPactApproval(next.authUrl);
    messageInput.focus();
}

function showMerchantAuthPrompt() {
    merchantAuthPrompt.style.display = 'block';
}

function hideMerchantAuthPrompt() {
    merchantAuthPrompt.style.display = 'none';
}

// ===== Chat Functions =====
function addMessage(role, content, allowHTML = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}-message`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (allowHTML) {
        contentDiv.innerHTML = content;
    } else {
        contentDiv.textContent = content;
    }

    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function addProductCards(products) {
    products.forEach(product => {
        const cardDiv = document.createElement('div');
        cardDiv.className = 'product-card';

        cardDiv.innerHTML = `
            <h4>${product.name || product.id}</h4>
            <p>${product.description || ''}</p>
            <div class="price">$${product.price || 'N/A'}</div>
        `;

        chatMessages.appendChild(cardDiv);
    });
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function addOrderConfirmation(order) {
    const confirmDiv = document.createElement('div');
    confirmDiv.className = 'order-confirmation';

    const orderUrl = order.permalink_url || '#';

    confirmDiv.innerHTML = `
        <h4>Order Confirmed!</h4>
        <p><strong>Order ID:</strong> ${order.id || 'N/A'}</p>
        <p><strong>Status:</strong> ${order.status || 'confirmed'}</p>
        ${order.permalink_url ? `<p><a href="${orderUrl}" target="_blank">View Order Details</a></p>` : ''}
    `;

    chatMessages.appendChild(confirmDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function updateCartSummary(summary) {
    if (!summary) {
        cartSummary.style.display = 'none';
        return;
    }

    cartSummary.style.display = 'block';

    // Display line items
    cartItems.innerHTML = '';
    if (summary.line_items && summary.line_items.length > 0) {
        summary.line_items.forEach(item => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'cart-item';
            const name = item.name || item.product_id;
            const qty = item.quantity || 1;
            itemDiv.textContent = `${name} x${qty}`;
            cartItems.appendChild(itemDiv);
        });

        // Check merchant auth when cart has items
        checkMerchantAuthForCart();
    }

    // Display total
    if (summary.total) {
        const amount = summary.total.amount || '0.00';
        const currency = summary.total.currency || 'USD';
        cartTotal.innerHTML = `<div class="cart-total">Total: ${currency} ${amount}</div>`;
    }
}

async function checkMerchantAuthForCart() {
    console.log('checkMerchantAuthForCart called');

    // If user has ever completed merchant auth, never show the banner again
    // The inline "authorize" buttons in chat messages are sufficient
    const hasCompletedAuthBefore = localStorage.getItem('merchantAuthCompleted') === 'true';
    if (hasCompletedAuthBefore) {
        console.log('User has completed merchant auth before, keeping banner hidden');
        hideMerchantAuthPrompt();
        return;
    }

    const isAuthorized = await checkMerchantAuth();
    console.log(`checkMerchantAuthForCart: isAuthorized=${isAuthorized}, merchantAuthInitiated=${merchantAuthInitiated}`);

    if (!isAuthorized && !merchantAuthInitiated) {
        console.log('Showing merchant auth banner (first time user)');
        showMerchantAuthPrompt();
    } else {
        console.log('Hiding merchant auth banner');
        hideMerchantAuthPrompt();
    }
}

async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    // Disable input
    messageInput.disabled = true;
    sendButton.disabled = true;

    // Add user message
    addMessage('user', message);
    messageInput.value = '';

    try {
        // Build headers
        const headers = {
            'Content-Type': 'application/json'
        };

        // Add auth header if user is logged in
        if (accessToken) {
            headers['Authorization'] = `Bearer ${accessToken}`;
        }

        // Send to API
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });

        if (!response.ok) {
            if (response.status === 401 && accessToken) {
                // Token expired, try to refresh
                accessToken = await auth0Client.getTokenSilently({ cacheMode: 'off' });
                throw new Error('Token expired, please retry');
            }
            throw new Error(`API error: ${response.status}`);
        }

        const data = await response.json();

        // Check if response indicates login required
        if (data.text && data.text.includes('ERROR: You must login')) {
            addMessage('assistant', 'To add items to your cart, please login first.');
            showLoginPrompt();
            return;
        }

        // The merchant's own agent needs the shopper's approval to look up their orders.
        // Our server has already explained why in data.text.
        if (data.pact_auth_required && data.pact_auth_url) {
            if (data.text) addMessage('assistant', data.text);
            addPactApproval(data.pact_auth_url);
            return;
        }

        // Merchant authorization needed to continue (e.g. cart or checkout was
        // attempted). Nothing else to show: the reply explains why.
        if (data.merchant_auth_required && data.merchant_auth_url && !data.merchant_auth_prompt) {
            const messageText = `${escapeHtml(data.text)} <a href="${data.merchant_auth_url}" class="merchant-auth-link">Connect to merchant</a>`;
            addMessage('assistant', messageText, true); // true = allow HTML
            return;
        }

        // Display assistant response
        if (data.text) {
            addMessage('assistant', data.text);
        }

        // Display product results
        if (data.results && data.results.length > 0) {
            addProductCards(data.results);
        }

        // Invite the shopper to connect to the merchant, after the products so
        // the list stays the first thing they see
        if (data.merchant_auth_required && data.merchant_auth_url && data.merchant_auth_prompt) {
            addMerchantConnectInvite(data.merchant_auth_prompt, data.merchant_auth_url);
        }

        // Update cart summary
        if (data.checkout_summary) {
            updateCartSummary(data.checkout_summary);
        }

        // Display order confirmation
        if (data.order) {
            addOrderConfirmation(data.order);
            cartSummary.style.display = 'none';
            hideMerchantAuthPrompt();
        }

    } catch (error) {
        console.error('Error sending message:', error);
        addMessage('assistant', 'Sorry, I encountered an error. Please try again.');
    } finally {
        messageInput.disabled = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

// ===== Event Listeners =====
// "Connect to merchant" links that arrive as HTML inside a chat message
chatMessages.addEventListener('click', (e) => {
    const link = e.target.closest && e.target.closest('a.merchant-auth-link:not(.merchant-connect-button)');
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    initiateMerchantAuth(link.href);
});

loginButton.addEventListener('click', login);
loginPromptButton.addEventListener('click', login);
logoutButton.addEventListener('click', logout);
connectMerchantButton.addEventListener('click', () => initiateMerchantAuth());

sendButton.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// ===== Initialize on Load =====
window.addEventListener('load', initAuth0);
