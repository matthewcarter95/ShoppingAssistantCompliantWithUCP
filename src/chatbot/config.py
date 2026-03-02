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


# Singleton settings instance
settings = Settings()
