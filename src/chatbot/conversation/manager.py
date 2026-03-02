"""Conversation session management with DynamoDB."""
import boto3
from typing import Optional
from datetime import datetime, timedelta

from ..config import settings
from ..utils.logger import setup_logger
from .state import ConversationState

logger = setup_logger(__name__, settings.log_level)


class ConversationManager:
    """Manages conversation sessions in DynamoDB."""

    def __init__(self, table_name: Optional[str] = None):
        """
        Initialize conversation manager.

        Args:
            table_name: DynamoDB table name (defaults to settings)
        """
        self.table_name = table_name or settings.dynamodb_table
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(self.table_name)

    def create_session(self, user_id: str, session_id: str) -> ConversationState:
        """
        Create a new conversation session.

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            New conversation state
        """
        ttl = int((datetime.now() + timedelta(days=30)).timestamp())
        state = ConversationState(
            user_id=user_id, session_id=session_id, ttl=ttl
        )

        self.table.put_item(Item=state.to_dynamodb_item())
        logger.info(f"Created session {session_id} for user {user_id}")
        return state

    def get_session(self, user_id: str, session_id: str) -> Optional[ConversationState]:
        """
        Retrieve a conversation session.

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            Conversation state if found, None otherwise
        """
        try:
            response = self.table.get_item(
                Key={"user_id": user_id, "session_id": session_id}
            )
            if "Item" in response:
                return ConversationState.from_dynamodb_item(response["Item"])
            return None
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    def update_session(self, state: ConversationState) -> None:
        """
        Update an existing conversation session.

        Args:
            state: Updated conversation state
        """
        state.updated_at = int(datetime.now().timestamp())
        self.table.put_item(Item=state.to_dynamodb_item())
        logger.debug(f"Updated session {state.session_id}")

    def get_or_create_session(
        self, user_id: str, session_id: str
    ) -> ConversationState:
        """
        Get existing session or create new one if not found.

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            Conversation state
        """
        state = self.get_session(user_id, session_id)
        if state is None:
            state = self.create_session(user_id, session_id)
        return state
