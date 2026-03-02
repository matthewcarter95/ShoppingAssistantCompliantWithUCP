"""FastAPI dependencies for JWT authentication."""

from typing import Dict, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from .jwt_validator import jwt_validator


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """
    Extract and validate JWT token from Authorization header.

    Returns:
        Dict with user info:
        {
            "sub": "auth0|...",
            "email": "user@example.com",
            "email_verified": true,
            ...
        }

    Raises:
        HTTPException: If token is invalid or missing
    """
    token = credentials.credentials

    try:
        payload = jwt_validator.validate_token(token)

        # Ensure email is present
        if "email" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing email claim"
            )

        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[Dict]:
    """
    Optional JWT authentication dependency.

    Returns:
        User dict if token is valid, None if no token provided

    Raises:
        HTTPException: If token is provided but invalid
    """
    if credentials is None:
        return None

    return await get_current_user(credentials)
