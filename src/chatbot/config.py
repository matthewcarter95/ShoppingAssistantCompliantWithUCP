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
    # Local development only: allow http and loopback merchants during discovery
    ucp_allow_insecure: bool = False

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
    merchant_auth0_domain: str = "auth0connectedapps.demo-connect.us"
    merchant_auth0_client_id: str = "PX3u5zLgnC39WzYFnGU6Aval5V9xabGd"
    merchant_auth0_audience: str = "api://ucp.session.service"
    merchant_auth0_scope: str = "openid profile email mock.ucp.shopping.checkout:manage mock.ucp.shopping.checkout:complete"

    # Custom claims on the merchant access token that carry checkout details.
    # Full claim = "<namespace>/<claim name>", e.g. https://demo.okta.com/name
    merchant_claims_namespace: str = "https://demo.okta.com"
    merchant_claim_name: str = "name"
    merchant_claim_email: str = "email"
    merchant_claim_address: str = "shippingAddress"

    # Chatbot base URL (Lambda Function URL)
    chatbot_base_url: str = "https://gscfl7ajbg3tudkoygerso7grq0epohi.lambda-url.us-east-1.on.aws"

    # PACT personal-agent identity (https://openpactprotocol.org). Off until a key is configured.
    # Issuer defaults to the Lambda Function URL (chatbot_base_url); the Provider matches `iss`
    # as an exact string, so changing it means re-registering with every Provider.
    pact_issuer: str = ""
    # SSM SecureString holding the private ES256 JWK (see scripts/gen_pact_key.py).
    pact_key_ssm_parameter: str = ""
    # SSM SecureString holding the secret that derives opaque per-user `sub` values.
    pact_sub_secret_ssm_parameter: str = ""
    # Local development only: take the values directly instead of from SSM.
    pact_private_jwk: str = ""
    pact_sub_secret: str = ""

    # Frontend URL for CORS and post-OAuth redirects
    frontend_url: str = "https://main.d7stwkdmkar4g.amplifyapp.com"

    @property
    def merchant_auth0_redirect_uri(self) -> str:
        """Merchant OAuth redirect URI - points to our backend callback endpoint."""
        return f"{self.chatbot_base_url}/webhooks/auth/callback"

    @property
    def pact_issuer_url(self) -> str:
        return (self.pact_issuer or self.chatbot_base_url).rstrip("/")


# Singleton settings instance
settings = Settings()
