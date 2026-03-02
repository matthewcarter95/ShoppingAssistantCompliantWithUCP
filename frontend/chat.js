// API endpoint configuration
// When opening as file://, use localhost. Otherwise use Lambda Function URL.
const API_BASE_URL = window.location.protocol === 'file:' || window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws';

// Session management
let sessionId = localStorage.getItem('sessionId');
const userId = 'default_user';

// Initialize session
async function initSession() {
    if (!sessionId) {
        try {
            const response = await fetch(`${API_BASE_URL}/session/new`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId }),
            });
            const data = await response.json();
            sessionId = data.session_id;
            localStorage.setItem('sessionId', sessionId);
            console.log('Created new session:', sessionId);
        } catch (error) {
            console.error('Failed to create session:', error);
            sessionId = generateUUID();
            localStorage.setItem('sessionId', sessionId);
        }
    }
}

// Generate UUID for fallback
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// DOM elements
const chatContainer = document.getElementById('chatContainer');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const cartSummary = document.getElementById('cartSummary');
const cartItems = document.getElementById('cartItems');
const cartTotal = document.getElementById('cartTotal');

// Add message to chat
function addMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}-message`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;

    messageDiv.appendChild(contentDiv);
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Add product cards
function addProductCards(products) {
    products.forEach(product => {
        const cardDiv = document.createElement('div');
        cardDiv.className = 'product-card';

        cardDiv.innerHTML = `
            <h4>${product.name || product.id}</h4>
            <p>${product.description || ''}</p>
            <div class="price">$${product.price || 'N/A'}</div>
        `;

        chatContainer.appendChild(cardDiv);
    });
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Add order confirmation
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

    chatContainer.appendChild(confirmDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Update cart summary
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
    }

    // Display total
    if (summary.total) {
        const amount = summary.total.amount || '0.00';
        const currency = summary.total.currency || 'USD';
        cartTotal.innerHTML = `<div class="cart-total">Total: ${currency} ${amount}</div>`;
    }
}

// Send message
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
        // Send to API
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                user_id: userId,
                message: message,
            }),
        });

        if (!response.ok) {
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
            // Clear cart summary on order completion
            cartSummary.style.display = 'none';
        }

    } catch (error) {
        console.error('Error sending message:', error);
        addMessage('assistant', 'Sorry, I encountered an error. Please try again.');
    } finally {
        // Re-enable input
        messageInput.disabled = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

// Event listeners
sendButton.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Initialize on load
window.addEventListener('load', async () => {
    await initSession();
    messageInput.focus();
});
