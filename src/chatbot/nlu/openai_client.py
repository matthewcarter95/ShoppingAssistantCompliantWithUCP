"""OpenAI API client for natural language understanding."""
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from ..config import settings
from ..utils.logger import setup_logger
from .tools import CHATBOT_TOOLS, SYSTEM_PROMPT

logger = setup_logger(__name__, settings.log_level)


class NLUClient:
    """Client for OpenAI chat completions with function calling."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize NLU client.

        Args:
            api_key: OpenAI API key (defaults to settings)
            model: Model name (defaults to settings)
        """
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.chatbot_model
        self.client = AsyncOpenAI(api_key=self.api_key)

    async def chat(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Send chat completion request with function calling.

        Args:
            messages: Conversation history in OpenAI format (can include tool_calls and tool responses)

        Returns:
            Dictionary with 'message' (assistant response) and optional 'tool_calls'
        """
        # Ensure system prompt is first
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

        try:
            # Convert tool_calls to proper format if present
            formatted_messages = []
            for msg in messages:
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    # Format assistant message with tool calls
                    formatted_msg = {
                        "role": "assistant",
                        "content": msg.get("content")
                    }
                    # Add tool_calls in OpenAI format
                    tool_calls = []
                    for tc in msg["tool_calls"]:
                        tool_calls.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"]
                            }
                        })
                    formatted_msg["tool_calls"] = tool_calls
                    formatted_messages.append(formatted_msg)
                elif msg.get("role") == "tool":
                    # Tool result message
                    formatted_messages.append({
                        "role": "tool",
                        "tool_call_id": msg["tool_call_id"],
                        "content": msg["content"]
                    })
                else:
                    # Regular message
                    formatted_messages.append(msg)

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                tools=CHATBOT_TOOLS,
                tool_choice="auto",
            )

            choice = response.choices[0]
            message = choice.message

            result = {
                "message": message.content or "",
                "tool_calls": [],
            }

            # Parse tool calls if present
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    result["tool_calls"].append({
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    })
                logger.info(f"OpenAI returned {len(result['tool_calls'])} tool calls")

            return result

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def format_messages(
        self, conversation_history: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Format conversation history for OpenAI API.

        Args:
            conversation_history: List of message dictionaries

        Returns:
            Formatted messages for OpenAI
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        for msg in conversation_history:
            if msg.get("role") in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg.get("content", ""),
                })

        return messages
