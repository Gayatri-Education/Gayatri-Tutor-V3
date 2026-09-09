"""Gayatri AI — SQLite-backed session persistence.

Stores and retrieves conversation sessions.
Schema: sessions (metadata), messages (full history).
Uses the DB_PATH configured in core.config.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("gayatri.session")


class SessionStore:
    """SQLite-backed session persistence.

    Tables:
        sessions: id, title, created_at, updated_at, message_count
        messages: id, session_id, role, content, agent_name, timestamp
    """

    def __init__(self, db_path: str | Path | None = None):
        from core.config import DB_PATH
        self.db_path = Path(db_path) if db_path else Path(DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_conn: sqlite3.Connection | None = None
        self._create_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create the database connection."""
        if self._db_conn is None:
            from core.db import get_safe_db_connection
            self._db_conn = get_safe_db_connection(self.db_path)
        return self._db_conn

    def _create_schema(self) -> None:
        """Create tables if they don't exist."""
        conn = self.conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                title       TEXT DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                message_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                agent_name  TEXT DEFAULT '',
                timestamp   TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
                ON messages(timestamp);
        """)
        conn.commit()
        logger.info(f"Session DB ready: {self.db_path}")

    def save_session(self, session_id: str, conversation: Any) -> None:
        """Save a conversation to the database.

        Args:
            session_id: Unique session identifier
            conversation: Conversation object with get_all() method
        """
        conn = self.conn
        now = datetime.now().isoformat()
        messages = conversation.get_all()

        # Upsert session
        conn.execute(
            """INSERT INTO sessions (id, title, created_at, updated_at, message_count)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   updated_at = excluded.updated_at,
                   message_count = excluded.message_count""",
            (
                session_id,
                messages[0]["content"][:80] if messages else "",
                now,
                now,
                len(messages),
            ),
        )

        # Replace all messages for this session
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        for msg in messages:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, agent_name, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    msg["role"],
                    msg["content"],
                    msg.get("agent_name", ""),
                    msg.get("timestamp", now),
                ),
            )
        conn.commit()
        logger.debug(f"Saved session {session_id}: {len(messages)} messages")

    def load_session(self, session_id: str) -> list[dict]:
        """Load all messages for a session.

        Returns:
            List of message dicts {role, content, agent_name, timestamp}
        """
        conn = self.conn
        cursor = conn.execute(
            "SELECT role, content, agent_name, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        )
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "agent_name": row["agent_name"],
                "timestamp": row["timestamp"],
            }
            for row in cursor.fetchall()
        ]

    def list_sessions(self) -> list[dict]:
        """List all sessions ordered by most recent first.

        Returns:
            List of {id, title, created_at, updated_at, message_count}
        """
        conn = self.conn
        cursor = conn.execute(
            "SELECT id, title, created_at, updated_at, message_count "
            "FROM sessions ORDER BY updated_at DESC"
        )
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message_count": row["message_count"],
            }
            for row in cursor.fetchall()
        ]

    def delete_session(self, session_id: str) -> None:
        """Delete a session and all its messages."""
        conn = self.conn
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        logger.info(f"Deleted session: {session_id}")

    def get_session_count(self) -> int:
        """Return total number of saved sessions."""
        conn = self.conn
        row = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
        return row[0]

    def close(self) -> None:
        """Close the database connection."""
        if self._db_conn:
            self._db_conn.close()
            self._db_conn = None


# Global session store instance
_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Get the global session store (singleton)."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store
