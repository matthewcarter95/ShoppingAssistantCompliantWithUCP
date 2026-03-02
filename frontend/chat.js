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

        auth0Client = await window.auth0.createAuth0Client({
            domain: AUTH0_DOMAIN,
            clientId: AUTH0_CLIENT_ID,
            authorizationParams: {
                redirect_uri: window.location.origin
            }
        });

        // Check if returning from Auth0 login redirect
        const query = window.location.search;
        if (query.includes('code=') && query.includes('state=')) {
            await handleAuthCallback();
        }

        // Check if user is authenticated
        const isAuthenticated = await auth0Client.isAuthenticated();

        authLoading.style.display = 'none';
        authButtons.style.display = 'block';

        if (isAuthenticated) {
            await handleAuthenticated();
        } else {
            showLoginPrompt();
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

        // Check if this is a merchant auth callback
        if (query.includes('state=') && sessionId) {
            const params = new URLSearchParams(query);
            const state = params.get('state');
            const code = params.get('code');

            if (state && state.startsWith(sessionId)) {
                // This is a merchant OAuth callback
                await handleMerchantAuthCallback(code, state);
                return;
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
        accessToken = await auth0Client.getTokenSilently();

        // Update UI
        userEmail.textContent = currentUser.email;
        userAvatar.src = currentUser.picture || 'https://via.placeholder.com/32';
        userProfile.style.display = 'flex';
        loginButton.style.display = 'none';
        loginPrompt.style.display = 'none';
        chatMessages.style.display = 'block';
        inputContainer.style.display = 'flex';

        // Initialize session
        await initSession();

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
    chatMessages.style.display = 'none';
    inputContainer.style.display = 'none';
    loginButton.style.display = 'block';
    userProfile.style.display = 'none';
}

// ===== Session Management =====
async function initSession() {
    sessionId = localStorage.getItem('sessionId');

    if (!sessionId) {
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
            console.log('Created new session:', sessionId);

        } catch (error) {
            console.error('Failed to create session:', error);
            addMessage('assistant', 'Failed to initialize session. Please refresh the page.');
        }
    }
}

// ===== Merchant OAuth Flow =====
async function checkMerchantAuth() {
    if (!sessionId || merchantAuthInitiated) return true;

    try {
        const response = await fetch(
            `${API_BASE_URL}/webhooks/auth/status?session_id=${sessionId}`,
            {
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                }
            }
        );

        if (!response.ok) return false;

        const data = await response.json();
        return data.authorized;

    } catch (error) {
        console.error('Error checking merchant auth:', error);
        return false;
    }
}

async function initiateMerchantAuth() {
    if (merchantAuthInitiated) return;

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

        if (!response.ok) {
            throw new Error('Failed to create merchant authorization');
        }

        const data = await response.json();

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

async function handleMerchantAuthCallback(code, state) {
    try {
        const codeVerifier = sessionStorage.getItem('merchant_code_verifier');
        const storedState = sessionStorage.getItem('merchant_state');

        if (!codeVerifier || state !== storedState) {
            throw new Error('Invalid state parameter');
        }

        // Exchange code for token
        const response = await fetch(`${API_BASE_URL}/webhooks/auth/callback`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({
                code: code,
                state: state,
                code_verifier: codeVerifier
            })
        });

        if (!response.ok) {
            throw new Error('Failed to complete merchant authorization');
        }

        // Clean up
        sessionStorage.removeItem('merchant_code_verifier');
        sessionStorage.removeItem('merchant_state');

        // Clean up URL
        window.history.replaceState({}, document.title, window.location.pathname);

        addMessage('assistant', 'Merchant account connected successfully! You can now complete your checkout.');

    } catch (error) {
        console.error('Merchant auth callback error:', error);
        addMessage('assistant', 'Failed to connect merchant account. Please try again.');
    }
}

function showMerchantAuthPrompt() {
    merchantAuthPrompt.style.display = 'block';
}

function hideMerchantAuthPrompt() {
    merchantAuthPrompt.style.display = 'none';
}

// ===== Chat Functions =====
function addMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}-message`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;

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
    const isAuthorized = await checkMerchantAuth();
    if (!isAuthorized && !merchantAuthInitiated) {
        showMerchantAuthPrompt();
    } else {
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
        // Send to API with Authorization header
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });

        if (!response.ok) {
            if (response.status === 401) {
                // Token expired, try to refresh
                accessToken = await auth0Client.getTokenSilently({ cacheMode: 'off' });
                throw new Error('Token expired, please retry');
            }
            throw new Error(`API error: ${response.status}`);
        }

        const data = await response.json();

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
