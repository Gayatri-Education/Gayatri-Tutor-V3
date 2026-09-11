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

            CREATE TABLE IF NOT EXISTS tutor_contexts (
                session_id           TEXT PRIMARY KEY,
                current_concept_id   TEXT DEFAULT '',
                current_concept_name TEXT DEFAULT '',
                concept_description  TEXT DEFAULT '',
                subject              TEXT DEFAULT '',
                mastery              REAL DEFAULT 0.3,
                waiting_for_answer   INTEGER DEFAULT 0,
                last_response_type   TEXT DEFAULT 'explain',
                last_attempt_correct INTEGER,
                updated_at           TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
                ON messages(timestamp);
        """)
        conn.commit()
        logger.info(f"Session DB ready: {self.db_path}")

    def save_session(self, session_id: str, conversation: Any, tutor_context: Any = None) -> None:
        """Save a conversation and optional tutor context to the database.

        Args:
            session_id: Unique session identifier
            conversation: Conversation object with get_all() method
            tutor_context: Optional TutorContext object
        """
        conn = self.conn
        now = datetime.now().isoformat()
        messages = conversation.get_all()

        # Upsert session
        conn.execute(
            """INSERT INTO sessions (id, title, created_at, updated_at, message_count)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   title = excluded.title,
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

        if tutor_context is not None:
            self.save_tutor_context(session_id, tutor_context)

    def save_tutor_context(self, session_id: str, ctx: Any) -> None:
        """Save tutor teaching state for a session."""
        if not ctx:
            return
        conn = self.conn
        now = datetime.now().isoformat()

        waiting = 1 if getattr(ctx, "waiting_for_answer", False) else 0
        last_correct = getattr(ctx, "last_attempt_correct", None)
        if last_correct is True:
            last_correct_int = 1
        elif last_correct is False:
            last_correct_int = 0
        else:
            last_correct_int = None

        conn.execute(
            """INSERT INTO tutor_contexts (
                   session_id, current_concept_id, current_concept_name,
                   concept_description, subject, mastery, waiting_for_answer,
                   last_response_type, last_attempt_correct, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   current_concept_id = excluded.current_concept_id,
                   current_concept_name = excluded.current_concept_name,
                   concept_description = excluded.concept_description,
                   subject = excluded.subject,
                   mastery = excluded.mastery,
                   waiting_for_answer = excluded.waiting_for_answer,
                   last_response_type = excluded.last_response_type,
                   last_attempt_correct = excluded.last_attempt_correct,
                   updated_at = excluded.updated_at""",
            (
                session_id,
                getattr(ctx, "current_concept_id", ""),
                getattr(ctx, "current_concept_name", ""),
                getattr(ctx, "concept_description", ""),
                getattr(ctx, "subject", ""),
                float(getattr(ctx, "mastery", 0.3)),
                waiting,
                getattr(ctx, "last_response_type", "explain"),
                last_correct_int,
                now,
            ),
        )
        conn.commit()
        logger.debug(f"Saved tutor context for session {session_id}")

    def load_tutor_context(self, session_id: str) -> Any:
        """Load tutor context for a session."""
        conn = self.conn
        row = conn.execute(
            """SELECT current_concept_id, current_concept_name, concept_description,
                      subject, mastery, waiting_for_answer, last_response_type,
                      last_attempt_correct
               FROM tutor_contexts WHERE session_id = ?""",
            (session_id,),
        ).fetchone()
        if not row:
            return None

        from core.tutor_engine import TutorContext
        last_correct = None
        if row["last_attempt_correct"] == 1:
            last_correct = True
        elif row["last_attempt_correct"] == 0:
            last_correct = False

        return TutorContext(
            current_concept_id=row["current_concept_id"] or "",
            current_concept_name=row["current_concept_name"] or "",
            concept_description=row["concept_description"] or "",
            subject=row["subject"] or "",
            mastery=float(row["mastery"] or 0.3),
            waiting_for_answer=bool(row["waiting_for_answer"]),
            last_response_type=row["last_response_type"] or "explain",
            last_attempt_correct=last_correct,
        )

    def load_session(self, session_id: str) -> list[dict]:
        """Load all messages for a session.

        Returns:
            List of message dicts {role, content, agent_name, timestamp}
        """
        conn = self.conn
        cursor = conn.execute(
            "SELECT role, content, agent_name, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY id",
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
        """Delete a session, its messages, and its tutor context."""
        conn = self.conn
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM tutor_contexts WHERE session_id = ?", (session_id,))
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
