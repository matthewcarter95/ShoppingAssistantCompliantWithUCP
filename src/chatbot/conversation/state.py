"""Conversation state data models."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class Message(BaseModel):
    """A single message in the conversation."""

    role: str  # "user", "assistant", or "system"
    content: str
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp()))


class ConversationState(BaseModel):
    """State for a conversation session."""

    user_id: str
    session_id: str
    checkout_id: Optional[str] = None
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    buyer_info: Optional[Dict[str, Any]] = None
    messages: List[Message] = Field(default_factory=list)
    status: str = "init"  # init -> shopping -> ready_to_pay -> completed
    created_at: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    updated_at: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    ttl: Optional[int] = None

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        message = Message(role=role, content=content)
        self.messages.append(message)
        self.updated_at = int(datetime.now().timestamp())

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format."""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "checkout_id": self.checkout_id,
            "line_items": self.line_items,
            "buyer_info": self.buyer_info,
            "messages": [m.model_dump() for m in self.messages],
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "ConversationState":
        """Create from DynamoDB item."""
        messages = [Message(**m) for m in item.get("messages", [])]
        return cls(
            user_id=item["user_id"],
            session_id=item["session_id"],
            checkout_id=item.get("checkout_id"),
            line_items=item.get("line_items", []),
            buyer_info=item.get("buyer_info"),
            messages=messages,
            status=item.get("status", "init"),
            created_at=item.get("created_at", int(datetime.now().timestamp())),
            updated_at=item.get("updated_at", int(datetime.now().timestamp())),
            ttl=item.get("ttl"),
        )
