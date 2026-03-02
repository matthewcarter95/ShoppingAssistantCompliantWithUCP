"""Auth module for JWT validation and OAuth flows."""

from .config import auth0_settings
from .jwt_validator import jwt_validator
from .dependencies import get_current_user, get_current_user_optional

__all__ = [
    "auth0_settings",
    "jwt_validator",
    "get_current_user",
    "get_current_user_optional",
]
