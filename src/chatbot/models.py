"""API request and response models."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    session_id: str = Field(..., description="Session identifier")
    message: str = Field(..., description="User message")
    user_id: str = Field(default="default_user", description="User identifier")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    text: str = Field(..., description="Assistant response text")
    results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Search results or other data"
    )
    checkout_summary: Optional[Dict[str, Any]] = Field(
        None, description="Current checkout summary"
    )
    order: Optional[Dict[str, Any]] = Field(
        None, description="Completed order information"
    )


class SessionResponse(BaseModel):
    """Response model for session info."""

    user_id: str
    session_id: str
    status: str
    checkout_id: Optional[str] = None
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: int
    updated_at: int


class NewSessionRequest(BaseModel):
    """Request model for creating a new session."""

    user_id: str = Field(default="default_user", description="User identifier")


class NewSessionResponse(BaseModel):
    """Response model for new session."""

    session_id: str
    user_id: str
