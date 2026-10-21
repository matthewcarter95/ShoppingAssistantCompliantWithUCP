"""API request and response models."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    session_id: str = Field(..., description="Session identifier")
    message: str = Field(..., description="User message")
    user_id: Optional[str] = Field(None, description="User identifier (extracted from JWT if not provided)")


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
    merchant_auth_required: bool = Field(
        False, description="Whether merchant authorization is required"
    )
    merchant_auth_url: Optional[str] = Field(
        None, description="Merchant authorization URL if auth is required"
    )
    merchant_auth_prompt: Optional[str] = Field(
        None, description="Explanation shown with the connect-to-merchant button"
    )
    pact_auth_required: bool = Field(
        False, description="The merchant's agent needs the shopper's approval before it can answer"
    )
    pact_auth_url: Optional[str] = Field(
        None, description="https link to the merchant's own sign-in and consent, opened in a popup"
    )


class PactResumeResponse(BaseModel):
    """Result of checking whether the shopper has approved access at the merchant."""

    status: str = Field(..., description="reply | pending | step_up | denied | expired | error | none")
    text: str = ""
    interval: int = 5
    auth_url: Optional[str] = None


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

    user_id: Optional[str] = Field(None, description="User identifier (extracted from JWT if not provided)")


class NewSessionResponse(BaseModel):
    """Response model for new session."""

    session_id: str
    user_id: str


class ErrorResponse(BaseModel):
    """Response model for authentication errors."""

    detail: str
    error_code: Optional[str] = None
