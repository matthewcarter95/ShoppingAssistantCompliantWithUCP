"""Pytest configuration and fixtures."""
import pytest
import os

# Set test environment variables
os.environ["OPENAI_API_KEY"] = "sk-test-key"
os.environ["DYNAMODB_TABLE"] = "TestConversationSessions"
os.environ["AWS_REGION"] = "us-east-1"
