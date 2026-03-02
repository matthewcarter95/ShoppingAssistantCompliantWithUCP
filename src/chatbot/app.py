"""FastAPI application for shopping assistant chatbot."""
import json
import uuid
import os
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import (
    ChatRequest,
    ChatResponse,
    SessionResponse,
    NewSessionRequest,
    NewSessionResponse,
)
from .ucp.client import UCPClient
from .nlu.openai_client import NLUClient
from .services.catalog_service import CatalogService
from .services.checkout_service import CheckoutService
from .services.payment_service import PaymentService
from .utils.logger import setup_logger

logger = setup_logger(__name__, settings.log_level)

# Check if running locally (no Lambda environment)
IS_LOCAL = os.environ.get("AWS_EXECUTION_ENV") is None

# Initialize FastAPI app
app = FastAPI(
    title="Shopping Assistant Chatbot",
    description="UCP-compliant shopping assistant with OpenAI NLU",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize clients and services
ucp_client = UCPClient()
nlu_client = NLUClient()

# Use in-memory session manager for local development
if IS_LOCAL:
    from .conversation.local_manager import LocalConversationManager
    conversation_manager = LocalConversationManager()
    logger.info("Using LocalConversationManager (in-memory) for local development")
else:
    from .conversation.manager import ConversationManager
    conversation_manager = ConversationManager()
    logger.info("Using ConversationManager (DynamoDB) for AWS Lambda")

catalog_service = CatalogService(ucp_client)
checkout_service = CheckoutService(ucp_client)
payment_service = PaymentService(ucp_client)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/agent-profile")
async def get_agent_profile():
    """Return UCP agent profile for this chatbot."""
    return {
        "id": "shopping-assistant-chatbot",
        "name": "Shopping Assistant",
        "version": "2026-01-11",
        "capabilities": {
            "shopping": {
                "version": "2026-01-11",
                "webhook_url": None  # No webhooks needed for chatbot
            }
        }
    }


@app.get("/discovery")
async def get_discovery():
    """Return UCP discovery document."""
    try:
        discovery = await ucp_client.discover()
        return discovery
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/new", response_model=NewSessionResponse)
async def create_new_session(request: NewSessionRequest):
    """Create a new conversation session."""
    session_id = str(uuid.uuid4())
    conversation_manager.create_session(request.user_id, session_id)
    return NewSessionResponse(session_id=session_id, user_id=request.user_id)


@app.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, user_id: str = "default_user"):
    """Retrieve session information."""
    state = conversation_manager.get_session(user_id, session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        user_id=state.user_id,
        session_id=state.session_id,
        status=state.status,
        checkout_id=state.checkout_id,
        line_items=state.line_items,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint.

    Processes user messages, calls OpenAI for NLU, executes tool calls,
    and returns assistant response with results.
    """
    try:
        # Get or create session
        state = conversation_manager.get_or_create_session(
            request.user_id, request.session_id
        )

        # Add user message to history
        state.add_message("user", request.message)

        # Format messages for OpenAI
        messages = nlu_client.format_messages(
            [{"role": m.role, "content": m.content} for m in state.messages]
        )

        # Initialize result tracking
        results = []
        checkout_summary = None
        order = None

        # Multi-turn tool calling loop (max 3 turns to prevent infinite loops)
        max_iterations = 3
        iteration = 0
        assistant_message = ""

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Tool calling iteration {iteration}")

            # Call OpenAI
            nlu_response = await nlu_client.chat(messages)
            assistant_message = nlu_response.get("message", "")

            # If no tool calls, we're done
            if not nlu_response.get("tool_calls"):
                logger.info("No tool calls, ending loop")
                break

            # Add assistant message with tool calls to messages
            messages.append({
                "role": "assistant",
                "content": assistant_message or None,
                "tool_calls": nlu_response.get("tool_calls")
            })

            # Process each tool call
            for tool_call in nlu_response["tool_calls"]:
                tool_name = tool_call["name"]
                tool_id = tool_call["id"]
                arguments = json.loads(tool_call["arguments"])

                logger.info(f"Executing tool: {tool_name} with args: {arguments}")

                tool_result = ""
                try:
                    if tool_name == "search_products":
                        products = await catalog_service.search_products(
                            arguments["query"]
                        )
                        results.extend(products)

                        # Build tool result with product IDs
                        if products:
                            product_list = ", ".join([f"{p['id']}" for p in products[:5]])
                            tool_result = f"Found {len(products)} products. Product IDs: {product_list}"
                        else:
                            tool_result = "No products found"

                    elif tool_name == "add_to_cart":
                        product_id = arguments["product_id"]
                        quantity = arguments.get("quantity", 1)
                        product_info = await catalog_service.get_product_by_id(product_id)

                        checkout_response = await checkout_service.add_item(
                            state, product_id, quantity, product_info
                        )
                        checkout_summary = await checkout_service.get_checkout_summary(
                            state
                        )
                        tool_result = f"Added {quantity} x {product_info.get('title', product_id)} to cart"

                    elif tool_name == "update_cart_quantity":
                        product_id = arguments["product_id"]
                        quantity = arguments["quantity"]

                        checkout_response = await checkout_service.update_item_quantity(
                            state, product_id, quantity
                        )
                        checkout_summary = await checkout_service.get_checkout_summary(
                            state
                        )
                        if quantity == 0:
                            tool_result = f"Removed {product_id} from cart"
                        else:
                            tool_result = f"Updated {product_id} quantity to {quantity}"

                    elif tool_name == "remove_from_cart":
                        product_id = arguments["product_id"]

                        checkout_response = await checkout_service.remove_item(
                            state, product_id
                        )
                        checkout_summary = await checkout_service.get_checkout_summary(
                            state
                        )
                        tool_result = f"Removed {product_id} from cart"

                    elif tool_name == "view_cart":
                        cart = await checkout_service.get_cart(state)
                        if cart:
                            item_count = len(cart.get("line_items", []))
                            tool_result = f"Cart has {item_count} items"
                            checkout_summary = cart
                        else:
                            tool_result = "Cart is empty"

                    elif tool_name == "apply_discount_code":
                        code = arguments["code"]
                        checkout_response = await checkout_service.apply_discount(
                            state, code
                        )
                        checkout_summary = await checkout_service.get_checkout_summary(
                            state
                        )
                        tool_result = f"Applied discount code: {code}"

                    elif tool_name == "complete_order":
                        # Store buyer info
                        buyer_info = {
                            "buyer_name": arguments["buyer_name"],
                            "buyer_email": arguments["buyer_email"],
                            "shipping_address": arguments["shipping_address"],
                        }
                        state.buyer_info = buyer_info

                        # Setup fulfillment with parsed address
                        shipping_address = payment_service._parse_address(
                            buyer_info["shipping_address"]
                        )
                        await checkout_service.setup_fulfillment(state, shipping_address)

                        # Complete checkout
                        order_response = await payment_service.complete_checkout(
                            state, buyer_info
                        )
                        order = order_response.get("order", {})
                        tool_result = f"Order completed successfully"

                except Exception as e:
                    logger.error(f"Tool execution error ({tool_name}): {e}")
                    tool_result = f"Error: {str(e)}"

                # Add tool result to messages for next OpenAI call
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_result
                })

        # Add final assistant message to history
        if assistant_message:
            state.add_message("assistant", assistant_message)

        # Update session in database
        conversation_manager.update_session(state)

        # Get checkout summary if we have an active checkout
        if state.checkout_id and not checkout_summary and not order:
            checkout_summary = await checkout_service.get_checkout_summary(state)

        return ChatResponse(
            text=assistant_message,
            results=results,
            checkout_summary=checkout_summary,
            order=order,
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    await ucp_client.close()
