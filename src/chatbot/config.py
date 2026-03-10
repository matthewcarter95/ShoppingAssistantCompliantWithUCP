"""Configuration management using Pydantic Settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required
    openai_api_key: str

    # UCP Configuration
    ucp_base_url: str = "https://n5je6mqzsskozc32cqdfetl42q0augte.lambda-url.us-east-1.on.aws/"
    ucp_agent_profile: str = "https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws/agent-profile"

    # OpenAI Configuration
    chatbot_model: str = "gpt-3.5-turbo"

    # DynamoDB Configuration
    dynamodb_table: str = "ConversationSessions"
    session_timeout_minutes: int = 30

    # Logging
    log_level: str = "INFO"

    # AWS Region
    aws_region: str = "us-east-1"

    # Shopping Assistant Auth0 Configuration (User Authentication)
    shopping_assistant_auth0_domain: str = "grocery-b2c.cic-demo-platform.auth0app.com"
    shopping_assistant_auth0_algorithms: list[str] = ["RS256"]
    # No audience needed for shopping assistant

    # Merchant OAuth Configuration (Authorization Code + PKCE)
    merchant_auth0_domain: str = "agentic-commerce-merchant.cic-demo-platform.auth0app.com"
    merchant_auth0_client_id: str = "U5xtIqc7cu707C28nQHeCKplg9ec2VPe"
    merchant_auth0_audience: str = "api://ucp.session.service"
    merchant_auth0_scope: str = "openid profile email ucp:scopes:checkout_session"

    # Chatbot base URL (Lambda Function URL)
    chatbot_base_url: str = "https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws"

    # Frontend URL for CORS and post-OAuth redirects
    frontend_url: str = "https://main.d7stwkdmkar4g.amplifyapp.com"

    @property
    def merchant_auth0_redirect_uri(self) -> str:
        """Merchant OAuth redirect URI - points to our backend callback endpoint."""
        return f"{self.chatbot_base_url}/webhooks/auth/callback"


# Singleton settings instance
settings = Settings()
