"""Gayatri AI — Tutor engine: context-aware teaching with LDG integration.

This module is NOT a "tutoring system" (prior art US20240135951A1).
It's a teaching strategy layer that provides concept context to agents.
No patented learning methods implemented.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("gayatri.tutor")


@dataclass
class TutorContext:
    """Current teaching state for a session."""
    current_concept_id: str = ""
    current_concept_name: str = ""
    concept_description: str = ""
    subject: str = ""
    mastery: float = 0.3
    waiting_for_answer: bool = False
    last_response_type: str = "explain"  # explain, question, practice, feedback

    def to_prompt_context(self) -> str:
        """Build a context string for the model system prompt."""
        if not self.current_concept_id:
            return ""

        lines = [
            f"Current teaching concept: {self.current_concept_name}",
            f"Description: {self.concept_description}",
            f"Student mastery: {int(self.mastery * 100)}%",
        ]

        if self.waiting_for_answer:
            lines.append("You just asked a question. Wait for the student's answer before continuing.")
        elif self.last_response_type == "explain":
            lines.append("After explaining, ask a comprehension question to check understanding.")
        elif self.last_response_type == "question":
            lines.append("Evaluate the student's answer. If correct, praise and move on. If wrong, gently correct and re-explain.")

        return "\n".join(lines)


class TutorEngine:
    """Orchestrates concept selection, progression, and mastery tracking.

    Wraps the Learning Dependency Graph with teaching logic.
    """

    def __init__(self, ldg: Any):
        self.ldg = ldg
        self.session_contexts: dict[str, TutorContext] = {}

    def get_or_create_context(self, session_id: str) -> TutorContext:
        """Get or create teaching context for a session."""
        if session_id not in self.session_contexts:
            self.session_contexts[session_id] = TutorContext()
        return self.session_contexts[session_id]

    def get_next_concept_for_session(self, session_id: str) -> Any:
        """Get the next concept to teach, advancing from current if mastered."""
        ctx = self.get_or_create_context(session_id)
        current_id = ctx.current_concept_id

        # If no current concept, or current is mastered, get next
        if not current_id or self.ldg.get_mastery(current_id) >= self.ldg.__class__.__dict__.get("MASTERY_THRESHOLD", 0.85):
            next_concept = self.ldg.get_next_concept(ctx.subject)
            if next_concept:
                # Advance context
                ctx.current_concept_id = next_concept.id
                ctx.current_concept_name = next_concept.name
                ctx.concept_description = next_concept.description
                ctx.mastery = self.ldg.get_mastery(next_concept.id)
                ctx.waiting_for_answer = False
                ctx.last_response_type = "explain"
                logger.info(f"Advanced to concept: {next_concept.name}")

        return self.ldg.get_concept(ctx.current_concept_id) if ctx.current_concept_id else None

    def record_student_response(self, session_id: str, correct: bool,
                                confidence: float = 1.0) -> float:
        """Record a student's answer and update mastery."""
        ctx = self.get_or_create_context(session_id)
        if not ctx.current_concept_id:
            return 0.0

        new_mastery = self.ldg.record_attempt(ctx.current_concept_id, correct, confidence)
        ctx.mastery = new_mastery
        ctx.last_response_type = "feedback" if ctx.waiting_for_answer else "explain"
        ctx.waiting_for_answer = False

        status = "correct" if correct else "incorrect"
        logger.info(
            f"Student {status} on {ctx.current_concept_name}: "
            f"mastery={new_mastery:.3f}"
        )
        return new_mastery

    def set_waiting_for_answer(self, session_id: str) -> None:
        """Mark that the tutor just asked a question and is waiting."""
        ctx = self.get_or_create_context(session_id)
        ctx.waiting_for_answer = True
        ctx.last_response_type = "question"

    def is_waiting_for_answer(self, session_id: str) -> bool:
        """Check if the tutor is waiting for a student answer."""
        ctx = self.get_or_create_context(session_id)
        return ctx.waiting_for_answer

    def get_session_summary(self, session_id: str) -> dict:
        """Get a summary of the current teaching session."""
        ctx = self.get_or_create_context(session_id)
        stats = self.ldg.get_progress_stats(ctx.subject)
        return {
            "current_concept": ctx.current_concept_name,
            "mastery": f"{int(ctx.mastery * 100)}%",
            "waiting_for_answer": ctx.waiting_for_answer,
            "progress": stats,
        }


# Global tutor engine (lazy-initialized with LDG)
_tutor_engine: TutorEngine | None = None


def get_tutor_engine(ldg: Any = None) -> TutorEngine:
    """Get the global tutor engine."""
    global _tutor_engine
    if _tutor_engine is None:
        if ldg is None:
            from core.knowledge_graph import LearningDependencyGraph
            ldg = LearningDependencyGraph()
        _tutor_engine = TutorEngine(ldg)
    return _tutor_engine
