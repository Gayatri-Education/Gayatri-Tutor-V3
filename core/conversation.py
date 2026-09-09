"""Gayatri AI — Per-session conversation history.

Maintains a rolling window of messages for each session.
Provides trimmed context for model input (respects token limits).
Thread-safe for single-user desktop use.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("gayatri.conversation")


@dataclass
class Message:
    """A single message in a conversation."""
    role: str  # "system", "user", "assistant"
    content: str
    agent_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Conversation:
    """Rolling conversation history for one session."""
    session_id: str
    max_messages: int = 20
    _messages: list[Message] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, role: str, content: str, agent_name: str = "") -> None:
        """Append a message and trim if over limit."""
        with self._lock:
            self._messages.append(Message(role=role, content=content, agent_name=agent_name))
            # Keep last system message + (max_messages - 1) turns
            if len(self._messages) > self.max_messages:
                # Preserve system messages, drop oldest user/assistant pairs
                system_msgs = [m for m in self._messages if m.role == "system"]
                other_msgs = [m for m in self._messages if m.role != "system"]
                num_keep = max(0, self.max_messages - len(system_msgs))
                keep = other_msgs[-num_keep:] if num_keep > 0 else []
                self._messages = system_msgs + keep
            logger.debug(f"[{self.session_id}] +{role} ({len(self._messages)} msgs)")

    def get_messages_for_model(self) -> list[dict]:
        """Return messages formatted for LLM input (list of {role, content})."""
        with self._lock:
            return [{"role": m.role, "content": m.content} for m in self._messages]

    def get_recent(self, n: int = 5) -> list[Message]:
        """Return the last n messages."""
        with self._lock:
            return list(self._messages[-n:])

    def clear(self) -> None:
        """Clear all messages."""
        with self._lock:
            self._messages.clear()
            logger.info(f"[{self.session_id}] Conversation cleared")

    def get_all(self) -> list[dict]:
        """Return all messages as dicts (for persistence/UI)."""
        with self._lock:
            return [
                {
                    "role": m.role,
                    "content": m.content,
                    "agent_name": m.agent_name,
                    "timestamp": m.timestamp,
                }
                for m in self._messages
            ]

    def __len__(self) -> int:
        with self._lock:
            return len(self._messages)


class ConversationStore:
    """Manages conversations for all active sessions.

    Usage:
        store = ConversationStore()
        conv = store.get("session-1")
        conv.add("user", "Hello")
        conv.add("assistant", "Hi there!")
        msgs = conv.get_messages_for_model()  # for model input
    """

    def __init__(self):
        self._conversations: dict[str, Conversation] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Conversation:
        """Get or create a conversation for the session."""
        with self._lock:
            if session_id not in self._conversations:
                self._conversations[session_id] = Conversation(session_id=session_id)
            return self._conversations[session_id]

    def new_session(self, session_id: str) -> Conversation:
        """Create a fresh conversation (clears any existing one)."""
        with self._lock:
            self._conversations[session_id] = Conversation(session_id=session_id)
            logger.info(f"New session: {session_id}")
            return self._conversations[session_id]

    def delete(self, session_id: str) -> None:
        """Remove a conversation."""
        with self._lock:
            self._conversations.pop(session_id, None)

    def list_sessions(self) -> list[str]:
        """List all active session IDs."""
        with self._lock:
            return list(self._conversations.keys())
