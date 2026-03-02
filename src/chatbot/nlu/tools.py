"""OpenAI function calling tool definitions."""
from typing import List, Dict, Any

SYSTEM_PROMPT = """You are a helpful shopping assistant. Help users find products and complete purchases.

Available functions: search_products, add_to_cart, update_cart_quantity, remove_from_cart, view_cart, apply_discount_code, complete_order.

CRITICAL: UNDERSTAND USER INTENT
- "show me X" / "what X do you have" = ONLY search, DO NOT add to cart
- "add X" / "I want X" / "buy X" = Search then add to cart (NEW item)
- "I only want 1" / "change to 3" / "make it 2" = Update existing item quantity
- "remove X" / "delete X" = Remove item from cart

FUNCTION USAGE RULES:

1. search_products - When user wants to BROWSE/SEE products
   - Examples: "show me roses", "what tulips do you have"
   - ONLY search, DO NOT add to cart
   - Let user decide if they want to add

2. add_to_cart - ONLY for adding NEW items user explicitly wants
   - Examples: "add red roses", "I want 2 tulips", "I'll take that"
   - NOT for: "show me", "what do you have"
   - NOT for updating quantities of existing items
   - Workflow: search_products first if needed, then add_to_cart

3. update_cart_quantity - When user wants to CHANGE quantity of existing item
   - Examples: "I only need 1", "change tulips to 3", "make it 2 roses"
   - Set quantity to 0 to remove
   - DO NOT use add_to_cart for this

4. remove_from_cart - When user wants to DELETE an item
   - Examples: "remove roses", "delete that", "take out the pot"

5. view_cart - Show current cart
   - Examples: "what's in my cart", "show cart", "what do I have"

6. apply_discount_code - Apply promo code
   - Examples: "apply code 10OFF", "use discount SAVE20"

7. complete_order - Checkout
   - Examples: "complete my order", "checkout", "place order"

IMPORTANT:
- Product IDs: bouquet_roses, pot_ceramic, bouquet_tulips, plant_succulent
- NEVER add to cart unless user explicitly asks to add/buy/take
- Use update_cart_quantity for changing quantities, NOT add_to_cart

Be conversational and friendly.
"""

CHATBOT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search for products in the catalog to show the user. Use this when user wants to BROWSE or SEE products (e.g., 'show me roses', 'what tulips do you have'). DO NOT automatically add products to cart after searching - wait for explicit add/buy intent from user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for products",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a NEW product to the shopping cart. Use this ONLY when user wants to add a new item they haven't added before. If item already exists in cart and user wants to change quantity, use update_cart_quantity instead. You must have the exact product_id from search results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The exact product ID to add to cart (e.g., 'bouquet_roses', 'pot_ceramic'). This must come from search results.",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity to add (default: 1)",
                        "default": 1,
                    },
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_cart_quantity",
            "description": "Update the quantity of an existing item in the cart. Use this when user wants to change how many of something they have (e.g., 'I only want 1', 'change tulips to 3', 'make it 2 roses'). Set quantity to 0 to remove the item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product ID to update (e.g., 'bouquet_roses')",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "New quantity (set to 0 to remove item)",
                    },
                },
                "required": ["product_id", "quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove an item completely from the cart. Use when user says 'remove X', 'delete X', 'take out X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product ID to remove",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_cart",
            "description": "Show the current cart contents. Use when user asks 'what's in my cart', 'show cart', 'what do I have'.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_discount_code",
            "description": "Apply a discount or promo code to the shopping cart. Use this when the user mentions a code like '10OFF', 'SAVE20', or says 'apply discount code'. The code parameter should be the code itself (e.g., '10OFF').",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The discount/promo code to apply (e.g., '10OFF', 'SAVE20')",
                    }
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_order",
            "description": "Complete the order and process payment",
            "parameters": {
                "type": "object",
                "properties": {
                    "buyer_name": {
                        "type": "string",
                        "description": "Full name of the buyer",
                    },
                    "buyer_email": {
                        "type": "string",
                        "description": "Email address of the buyer",
                    },
                    "shipping_address": {
                        "type": "string",
                        "description": "Full shipping address",
                    },
                },
                "required": ["buyer_name", "buyer_email", "shipping_address"],
            },
        },
    },
]
