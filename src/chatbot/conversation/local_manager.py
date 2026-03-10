"""In-memory conversation manager for local development."""
from typing import Dict, Optional
from datetime import datetime, timedelta

from ..utils.logger import setup_logger
from ..config import settings
from .state import ConversationState

logger = setup_logger(__name__, settings.log_level)


class LocalConversationManager:
    """In-memory conversation manager for local development without DynamoDB."""

    def __init__(self):
        """Initialize local conversation manager with in-memory storage."""
        self._sessions: Dict[str, ConversationState] = {}
        logger.info("Using in-memory session storage (local development)")

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

        key = f"{user_id}:{session_id}"
        self._sessions[key] = state
        logger.info(f"Created in-memory session {session_id} for user {user_id}")
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
        key = f"{user_id}:{session_id}"
        return self._sessions.get(key)

    def update_session(self, state: ConversationState) -> None:
        """
        Update an existing conversation session.

        Args:
            state: Updated conversation state
        """
        state.updated_at = int(datetime.now().timestamp())
        key = f"{state.user_id}:{state.session_id}"
        self._sessions[key] = state
        logger.debug(f"Updated in-memory session {state.session_id}")

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

    def get_session_by_id(self, session_id: str) -> Optional[ConversationState]:
        """
        Retrieve a conversation session by session_id alone.

        This is useful for OAuth callbacks where we have the session_id
        from the state parameter but don't know the user_id yet.

        Args:
            session_id: Session identifier

        Returns:
            Conversation state if found, None otherwise
        """
        # Iterate through all sessions to find matching session_id
        for state in self._sessions.values():
            if state.session_id == session_id:
                return state
        return None
