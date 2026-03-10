"""Auth0 configuration for shopping assistant and merchant OAuth."""

from typing import List
from pydantic_settings import BaseSettings


class Auth0Settings(BaseSettings):
    """Auth0 configuration settings."""

    # Shopping Assistant Auth0 Configuration (User Authentication)
    shopping_assistant_auth0_domain: str = "grocery-b2c.cic-demo-platform.auth0app.com"
    shopping_assistant_auth0_algorithms: List[str] = ["RS256"]
    # No audience needed for shopping assistant

    # Merchant OAuth Configuration (Authorization Code + PKCE)
    # Note: redirect_uri is now computed from chatbot_base_url in config.py
    merchant_auth0_domain: str = "agentic-commerce-merchant.cic-demo-platform.auth0app.com"
    merchant_auth0_client_id: str = "U5xtIqc7cu707C28nQHeCKplg9ec2VPe"
    merchant_auth0_audience: str = "api://ucp.session.service"
    merchant_auth0_scope: str = "openid profile email ucp:scopes:checkout_session"

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
auth0_settings = Auth0Settings()
