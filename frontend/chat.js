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
            addMessage('assistant', 'Merchant account connected successfully! You can now add items to your cart.');
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

async function initiateMerchantAuth() {
    if (merchantAuthInitiated) {
        console.log('Merchant auth already initiated, skipping');
        return;
    }

    console.log(`Initiating merchant auth for session: ${sessionId}`);
    merchantAuthInitiated = true;

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

        // Store code_verifier in sessionStorage
        sessionStorage.setItem('merchant_code_verifier', data.code_verifier);
        sessionStorage.setItem('merchant_state', data.state);

        // Redirect to authorization URL
        window.location.href = data.authorization_url;

    } catch (error) {
        console.error('Error initiating merchant auth:', error);
        addMessage('assistant', 'Failed to initiate merchant authorization. Please try again.');
        merchantAuthInitiated = false;
    }
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

        // Check if merchant authorization is required
        if (data.merchant_auth_required && data.merchant_auth_url) {
            // Display message with authorization link
            const messageText = `${data.text} <a href="${data.merchant_auth_url}" class="merchant-auth-link">Click here to authorize</a>`;
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
loginButton.addEventListener('click', login);
loginPromptButton.addEventListener('click', login);
logoutButton.addEventListener('click', logout);
connectMerchantButton.addEventListener('click', initiateMerchantAuth);

sendButton.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// ===== Initialize on Load =====
window.addEventListener('load', initAuth0);
