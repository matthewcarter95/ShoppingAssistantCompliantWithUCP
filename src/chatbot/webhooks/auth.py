"""Webhooks for merchant OAuth authorization."""

from typing import Dict, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..auth.dependencies import get_current_user
from ..auth.merchant_oauth import merchant_oauth_client
from ..conversation.manager import get_session_manager
from ..utils.logger import setup_logger
from ..config import settings
from ..services.popup_page import render_callback_page

logger = setup_logger(__name__, settings.log_level)


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
    code_verifier: Optional[str] = None  # Optional, will be retrieved from session if not provided


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
    user_id = user["email"]
    session_state = manager.get_session(user_id, session_id)

    if not session_state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    # Verify session belongs to user
    if session_state.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to user"
        )

    # Check merchant auth
    merchant_auth = session_state.merchant_auth
    logger.info(f"Checking merchant auth for session {session_id}: has_merchant_auth={bool(merchant_auth)}, has_token={bool(merchant_auth and merchant_auth.get('access_token')) if merchant_auth else False}")

    if not merchant_auth or not merchant_auth.get("access_token"):
        logger.warning(f"Merchant auth not found or missing token for session {session_id}")
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

                manager.update_session(session_state)

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


def _callback_page(success: bool, session_id: Optional[str] = None, error_code: Optional[str] = None) -> HTMLResponse:
    """The OAuth callback response. Never cached: it is tied to a one-time code."""
    return HTMLResponse(
        render_callback_page(settings.frontend_url, success, session_id, error_code),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/callback")
async def handle_oauth_callback(
    code: str,
    state: str,
    request: Request
):
    """
    Handle OAuth callback redirect from merchant authorization.

    This endpoint receives the authorization code from merchant Auth0,
    exchanges it for tokens, stores them in the session, and returns a small
    page that reports the outcome to the chat window that opened this popup
    (and closes itself), or sends a plain tab back to the chat.

    Args:
        code: Authorization code from Auth0
        state: State parameter containing session_id and CSRF token
        request: FastAPI request object

    Returns:
        HTMLResponse: the popup result page

    Note: This is a GET endpoint because OAuth callbacks are browser redirects.
    It doesn't require shopping assistant authentication because:
    1. The user was authenticated when they initiated the flow
    2. We stored the PKCE verifier in their session (keyed by session_id from state)
    3. We can look up the session by session_id alone (extracted from state)
    """
    logger.info(f"OAuth callback received - state: {state[:50]}...")

    try:
        # Parse state parameter to get session ID
        session_id, csrf_token, intent = merchant_oauth_client.parse_state(state)
        logger.info(f"Parsed state - session_id: {session_id}, intent: {intent}")
    except ValueError as e:
        logger.error(f"Invalid state parameter: {str(e)}")
        # Redirect to frontend with error
        return _callback_page(success=False, error_code="invalid_state")

    # Load session by session_id (without requiring user_id)
    manager = get_session_manager()
    logger.info(f"Looking up session by ID: {session_id}")
    session_state = manager.get_session_by_id(session_id)

    if not session_state:
        logger.error(f"Session not found for session_id: {session_id}")
        return _callback_page(success=False, error_code="session_not_found")

    logger.info(f"Session found - user_id: {session_state.user_id}")

    # Get code_verifier from session
    logger.info("Retrieving code verifier from session")
    if session_state.merchant_auth and session_state.merchant_auth.get("pending_code_verifier"):
        code_verifier = session_state.merchant_auth["pending_code_verifier"]
        logger.info("Code verifier found in session")
    else:
        logger.error("Code verifier not found in session")
        return _callback_page(success=False, error_code="missing_code_verifier")

    # Exchange authorization code for tokens
    try:
        logger.info("Exchanging authorization code for tokens")
        token_response = await merchant_oauth_client.exchange_code_for_token(
            code,
            code_verifier
        )
        logger.info("Successfully exchanged code for tokens")
    except Exception as e:
        logger.error(f"Failed to exchange authorization code: {str(e)}")
        return _callback_page(success=False, error_code="token_exchange_failed")

    # Store tokens in session
    logger.info(f"Storing merchant auth tokens for session {session_id}")
    session_state.merchant_auth = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "expires_at": merchant_oauth_client.calculate_expiration(token_response["expires_in"]),
        "merchant_user": {
            "email": session_state.user_id,  # Use user_id from session
            "name": session_state.user_id,
        }
    }

    # Clear the pending code_verifier now that we've used it
    # Note: The new dict above doesn't have these, but we're being defensive
    if "pending_code_verifier" in session_state.merchant_auth:
        del session_state.merchant_auth["pending_code_verifier"]
    if "pending_state" in session_state.merchant_auth:
        del session_state.merchant_auth["pending_state"]

    logger.info(f"Updating session {session_id} with merchant auth")
    manager.update_session(session_state)
    logger.info(f"Session {session_id} updated successfully with merchant auth")

    # Tell the chat window (this runs in its popup) and close
    return _callback_page(success=True, session_id=session_id)


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
    session_state = manager.get_session(user["email"], session_id)

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

    # The callback reads the verifier from the session (it runs in a popup with
    # no access to this page's sessionStorage), so park it there
    if not session_state.merchant_auth:
        session_state.merchant_auth = {}
    session_state.merchant_auth["pending_code_verifier"] = code_verifier
    session_state.merchant_auth["pending_state"] = state
    manager.update_session(session_state)

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
