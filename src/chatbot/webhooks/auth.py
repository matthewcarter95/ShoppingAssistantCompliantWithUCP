"""Webhooks for merchant OAuth authorization."""

from typing import Dict, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth.dependencies import get_current_user
from ..auth.merchant_oauth import merchant_oauth_client
from ..conversation.manager import get_session_manager


router = APIRouter(prefix="/webhooks/auth", tags=["webhooks"])


class MerchantAuthStatus(BaseModel):
    """Response model for merchant auth status."""
    authorized: bool
    merchant_user: Optional[Dict] = None
    expires_at: Optional[str] = None


class OAuthCallbackRequest(BaseModel):
    """Request model for OAuth callback."""
    code: str
    state: str
    code_verifier: str


class OAuthCreateRequest(BaseModel):
    """Request model for creating OAuth authorization."""
    checkout_id: Optional[str] = None
    intent: str = "create"


class OAuthCreateResponse(BaseModel):
    """Response model for OAuth create."""
    authorization_url: str
    code_verifier: str
    state: str


@router.get("/status", response_model=MerchantAuthStatus)
async def check_merchant_auth_status(
    session_id: str,
    user: Dict = Depends(get_current_user)
):
    """
    Check merchant authorization status for a session.

    Args:
        session_id: Session ID to check
        user: Authenticated user from JWT

    Returns:
        MerchantAuthStatus with authorization details
    """
    manager = get_session_manager()
    session_state = await manager.load_session(session_id)

    if not session_state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    # Verify session belongs to user
    if session_state.user_id != user["email"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to user"
        )

    # Check merchant auth
    merchant_auth = session_state.merchant_auth

    if not merchant_auth or not merchant_auth.get("access_token"):
        return MerchantAuthStatus(authorized=False)

    # Check if token is expired
    expires_at = merchant_auth.get("expires_at")
    if expires_at and merchant_oauth_client.is_token_expired(expires_at):
        # Try to refresh token
        refresh_token = merchant_auth.get("refresh_token")
        if refresh_token:
            try:
                token_response = await merchant_oauth_client.refresh_access_token(refresh_token)

                # Update session with new token
                session_state.merchant_auth = {
                    "access_token": token_response["access_token"],
                    "refresh_token": token_response.get("refresh_token", refresh_token),
                    "expires_at": merchant_oauth_client.calculate_expiration(token_response["expires_in"]),
                    "merchant_user": merchant_auth.get("merchant_user"),
                }

                await manager.save_session(session_state)

                return MerchantAuthStatus(
                    authorized=True,
                    merchant_user=session_state.merchant_auth.get("merchant_user"),
                    expires_at=session_state.merchant_auth["expires_at"]
                )
            except Exception:
                # Refresh failed, return unauthorized
                return MerchantAuthStatus(authorized=False)
        else:
            return MerchantAuthStatus(authorized=False)

    return MerchantAuthStatus(
        authorized=True,
        merchant_user=merchant_auth.get("merchant_user"),
        expires_at=expires_at
    )


@router.post("/callback")
async def handle_oauth_callback(
    request: OAuthCallbackRequest,
    user: Dict = Depends(get_current_user)
):
    """
    Handle OAuth callback from merchant authorization.

    Args:
        request: OAuth callback request with code and state
        user: Authenticated user from JWT

    Returns:
        Success message
    """
    try:
        # Parse state parameter
        session_id, csrf_token, intent = merchant_oauth_client.parse_state(request.state)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state parameter: {str(e)}"
        )

    # Load session
    manager = get_session_manager()
    session_state = await manager.load_session(session_id)

    if not session_state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    # Verify session belongs to user
    if session_state.user_id != user["email"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to user"
        )

    # Exchange authorization code for tokens
    try:
        token_response = await merchant_oauth_client.exchange_code_for_token(
            request.code,
            request.code_verifier
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange authorization code: {str(e)}"
        )

    # Store tokens in session
    session_state.merchant_auth = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "expires_at": merchant_oauth_client.calculate_expiration(token_response["expires_in"]),
        "merchant_user": {
            "email": user["email"],  # Use shopping assistant user email for now
            "name": user.get("name", user["email"]),
        }
    }

    await manager.save_session(session_state)

    return {
        "success": True,
        "message": "Merchant authorization successful",
        "expires_at": session_state.merchant_auth["expires_at"]
    }


@router.post("/create", response_model=OAuthCreateResponse)
async def create_merchant_authorization(
    request: OAuthCreateRequest,
    session_id: str,
    user: Dict = Depends(get_current_user)
):
    """
    Initiate merchant OAuth authorization flow.

    Args:
        request: OAuth create request with intent
        session_id: Session ID for state tracking
        user: Authenticated user from JWT

    Returns:
        OAuthCreateResponse with authorization URL and PKCE parameters
    """
    # Verify session exists and belongs to user
    manager = get_session_manager()
    session_state = await manager.load_session(session_id)

    if not session_state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    if session_state.user_id != user["email"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to user"
        )

    # Generate PKCE parameters
    code_verifier, code_challenge = merchant_oauth_client.generate_pkce_pair()

    # Generate state
    state = merchant_oauth_client.generate_state(session_id, request.intent)

    # Build authorization URL
    authorization_url = merchant_oauth_client.build_authorization_url(
        state=state,
        code_challenge=code_challenge,
        intent=request.intent
    )

    return OAuthCreateResponse(
        authorization_url=authorization_url,
        code_verifier=code_verifier,
        state=state
    )


@router.get("/check")
async def check_merchant_token(
    session_id: str,
    user: Dict = Depends(get_current_user)
):
    """
    Quick check if merchant token exists and is valid.

    Args:
        session_id: Session ID to check
        user: Authenticated user from JWT

    Returns:
        Dict with validation status
    """
    return await check_merchant_auth_status(session_id, user)
