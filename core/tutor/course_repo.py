"""Course and Assessment Data Repository.

Additive SQLite storage for K-12 curriculum, questions, diagnostic attempts,
mastery records, and progress event streams.
Uses thread-safe SQLite connection management matching core.session.SessionStore.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.config import DATA_DIR
from core.db import get_safe_db_connection
from core.tutor.course_loader import ParsedCourse, ParsedQuizQuestion, ParsedTopic

logger = logging.getLogger("gayatri.tutor.repo")


class CourseRepository:
    """Manages persistence for K-12 courses, questions, attempts, and mastery."""

    def __init__(self, db_path: Path | str | None = None):
        if db_path is None:
            self.db_path = DATA_DIR / "gayatri.db"
        else:
            self.db_path = Path(db_path) if str(db_path) != ":memory:" else ":memory:"
        self._lock = threading.RLock()
        self._db_conn: sqlite3.Connection | None = None
        self._init_tables()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create the thread-safe database connection."""
        with self._lock:
            if self._db_conn is None:
                self._db_conn = get_safe_db_connection(self.db_path)
            return self._db_conn

    def _init_tables(self) -> None:
        """Create additive tables if they don't already exist."""
        with self._lock:
            with self.conn:
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS k12_courses (
                        id TEXT PRIMARY KEY,
                        subject TEXT NOT NULL,
                        grade INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        difficulty_default INTEGER DEFAULT 2,
                        source_file TEXT,
                        created_at REAL NOT NULL
                    );
                    """
                )
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS k12_topics (
                        id TEXT PRIMARY KEY,
                        course_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        anchor TEXT NOT NULL,
                        display_order INTEGER DEFAULT 1,
                        FOREIGN KEY (course_id) REFERENCES k12_courses(id) ON DELETE CASCADE
                    );
                    """
                )
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS k12_questions (
                        id TEXT PRIMARY KEY,
                        topic_id TEXT NOT NULL,
                        type TEXT DEFAULT 'mcq',
                        difficulty INTEGER DEFAULT 2,
                        question TEXT NOT NULL,
                        options_json TEXT NOT NULL,
                        answer_index INTEGER NOT NULL,
                        explanation TEXT,
                        FOREIGN KEY (topic_id) REFERENCES k12_topics(id) ON DELETE CASCADE
                    );
                    """
                )
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS k12_diagnostic_attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id TEXT NOT NULL,
                        topic_id TEXT NOT NULL,
                        question_id TEXT NOT NULL,
                        is_correct INTEGER NOT NULL,
                        response_time_ms INTEGER DEFAULT 0,
                        created_at REAL NOT NULL
                    );
                    """
                )
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS k12_topic_mastery (
                        student_id TEXT NOT NULL,
                        topic_id TEXT NOT NULL,
                        mastery_score REAL NOT NULL,
                        confidence REAL DEFAULT 0.5,
                        last_updated REAL NOT NULL,
                        PRIMARY KEY (student_id, topic_id)
                    );
                    """
                )
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS k12_progress_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id TEXT NOT NULL,
                        topic_id TEXT,
                        event_type TEXT NOT NULL,
                        payload_json TEXT,
                        created_at REAL NOT NULL
                    );
                    """
                )

    # ── Course Management ────────────────────────────────────────────────

    def save_course(self, course: ParsedCourse) -> None:
        """Upsert a parsed course, its topics, and quiz questions."""
        with self._lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO k12_courses (id, subject, grade, title, difficulty_default, source_file, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        course.course_id,
                        course.subject,
                        course.grade,
                        course.title,
                        course.difficulty_default,
                        course.source_file,
                        time.time(),
                    ),
                )

                for topic in course.topics:
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO k12_topics (id, course_id, title, anchor, display_order)
                        VALUES (?, ?, ?, ?, ?);
                        """,
                        (topic.id, course.course_id, topic.title, topic.anchor, topic.order),
                    )

                    for q in topic.questions:
                        self.conn.execute(
                            """
                            INSERT OR REPLACE INTO k12_questions (id, topic_id, type, difficulty, question, options_json, answer_index, explanation)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                            """,
                            (
                                q.id,
                                q.topic_id,
                                q.type,
                                q.difficulty,
                                q.question,
                                json.dumps(q.options),
                                q.answer,
                                q.explanation,
                            ),
                        )
            logger.info(f"Course '{course.title}' ({course.course_id}) saved.")

    def list_courses(self) -> list[dict[str, Any]]:
        """List all ingested courses."""
        with self._lock:
            cursor = self.conn.execute("SELECT id, subject, grade, title, difficulty_default, source_file, created_at FROM k12_courses ORDER BY grade, subject, title;")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_course(self, course_id: str) -> dict[str, Any] | None:
        """Get course metadata by course_id."""
        with self._lock:
            cursor = self.conn.execute("SELECT * FROM k12_courses WHERE id = ?;", (course_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_topics_for_course(self, course_id: str) -> list[dict[str, Any]]:
        """Get topics belonging to a course ordered by display_order."""
        with self._lock:
            cursor = self.conn.execute("SELECT * FROM k12_topics WHERE course_id = ? ORDER BY display_order ASC;", (course_id,))
            return [dict(row) for row in cursor.fetchall()]

    # ── Questions & Diagnostic Access ───────────────────────────────────

    def get_questions_for_topic(self, topic_id: str, difficulty: int | None = None) -> list[dict[str, Any]]:
        """Retrieve question bank for a specific topic, optionally filtered by difficulty."""
        with self._lock:
            if difficulty is not None:
                cursor = self.conn.execute(
                    "SELECT * FROM k12_questions WHERE topic_id = ? AND difficulty = ? ORDER BY id;",
                    (topic_id, difficulty),
                )
            else:
                cursor = self.conn.execute(
                    "SELECT * FROM k12_questions WHERE topic_id = ? ORDER BY difficulty ASC, id ASC;",
                    (topic_id,),
                )
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                d["options"] = json.loads(d["options_json"])
                results.append(d)
            return results

    # ── Mastery & Diagnostic Attempts ────────────────────────────────────

    def record_attempt(
        self,
        student_id: str,
        topic_id: str,
        question_id: str,
        is_correct: bool,
        response_time_ms: int = 0,
    ) -> int:
        """Log a question attempt (diagnostic or in-line practice)."""
        with self._lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO k12_diagnostic_attempts (student_id, topic_id, question_id, is_correct, response_time_ms, created_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (student_id, topic_id, question_id, 1 if is_correct else 0, response_time_ms, time.time()),
                )
                return cursor.lastrowid

    def get_mastery(self, student_id: str, topic_id: str) -> dict[str, Any] | None:
        """Fetch current mastery score and confidence for a student on a given topic."""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT mastery_score, confidence, last_updated FROM k12_topic_mastery WHERE student_id = ? AND topic_id = ?;",
                (student_id, topic_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def set_mastery(
        self,
        student_id: str,
        topic_id: str,
        mastery_score: float,
        confidence: float = 0.5,
    ) -> None:
        """Upsert student topic mastery."""
        clamped_score = max(0.0, min(1.0, float(mastery_score)))
        with self._lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO k12_topic_mastery (student_id, topic_id, mastery_score, confidence, last_updated)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (student_id, topic_id, clamped_score, confidence, time.time()),
                )

    def log_event(self, student_id: str, topic_id: str | None, event_type: str, payload: dict | None = None) -> None:
        """Emit an analytics event into the progress event log."""
        with self._lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO k12_progress_events (student_id, topic_id, event_type, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (student_id, topic_id, event_type, json.dumps(payload or {}), time.time()),
                )


# Global singleton instance
course_repo = CourseRepository()
