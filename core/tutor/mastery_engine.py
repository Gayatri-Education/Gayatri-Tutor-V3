"""Bayesian Knowledge Tracing (BKT) & Adaptive Tutoring Engine.

Implements the K-12 adaptive intelligence:
- BKT-style continuous mastery score updates per (student, topic)
- Difficulty-weighted learning rate scaling
- 3-tier pedagogical scaffolding (Remedial, Core, Advanced)
- Dynamic system prompt construction with level:N curriculum injection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from core.tutor.course_repo import CourseRepository, course_repo

logger = logging.getLogger("gayatri.tutor.mastery")


@dataclass
class MasteryUpdateResult:
    student_id: str
    topic_id: str
    previous_mastery: float
    new_mastery: float
    is_correct: bool
    difficulty: int
    tier: str  # "Remedial" | "Core" | "Advanced"


class BKTMasteryEngine:
    """Lightweight Bayesian Knowledge Tracing engine for adaptive learning."""

    DEFAULT_LEARNING_RATE: float = 0.15
    DEFAULT_PRIOR_MASTERY: float = 0.30

    def __init__(self, repo: CourseRepository | None = None, learning_rate: float = DEFAULT_LEARNING_RATE):
        self.repo = repo or course_repo
        self.learning_rate = learning_rate

    @staticmethod
    def difficulty_weight(difficulty: int) -> float:
        """Calculate weight multiplier for difficulty level 1 through 5.

        Level 1: 0.8
        Level 2: 1.0
        Level 3: 1.2
        Level 4: 1.4
        Level 5: 1.6
        """
        clamped = max(1, min(5, int(difficulty)))
        return 0.6 + (clamped * 0.2)

    def get_student_mastery(self, student_id: str, topic_id: str) -> float:
        """Retrieve current mastery score or default prior."""
        record = self.repo.get_mastery(student_id, topic_id)
        if record:
            return float(record["mastery_score"])
        return self.DEFAULT_PRIOR_MASTERY

    def get_mastery_tier(self, mastery: float) -> str:
        """Determine pedagogical tier based on mastery score."""
        if mastery < 0.40:
            return "Remedial"
        elif mastery < 0.70:
            return "Core"
        else:
            return "Advanced"

    def update_mastery(
        self,
        student_id: str,
        topic_id: str,
        is_correct: bool,
        difficulty: int = 2,
    ) -> MasteryUpdateResult:
        """Update student mastery based on answer correctness and difficulty.

        Formulas:
        - Correct: M' = M + alpha * (1 - M) * w_diff
        - Incorrect: M' = M - alpha * M * (1 / w_diff)
        Clamped to [0.0, 1.0].
        """
        current_m = self.get_student_mastery(student_id, topic_id)
        w_diff = self.difficulty_weight(difficulty)

        if is_correct:
            delta = self.learning_rate * (1.0 - current_m) * w_diff
            new_m = current_m + delta
        else:
            delta = self.learning_rate * current_m * (1.0 / w_diff)
            new_m = current_m - delta

        new_m = round(max(0.0, min(1.0, new_m)), 3)
        tier = self.get_mastery_tier(new_m)

        # Persist updated mastery
        self.repo.set_mastery(
            student_id=student_id,
            topic_id=topic_id,
            mastery_score=new_m,
            confidence=0.85,
        )

        # Log event
        self.repo.log_event(
            student_id=student_id,
            topic_id=topic_id,
            event_type="mastery_updated",
            payload={
                "previous_mastery": current_m,
                "new_mastery": new_m,
                "is_correct": is_correct,
                "difficulty": difficulty,
                "tier": tier,
            },
        )

        return MasteryUpdateResult(
            student_id=student_id,
            topic_id=topic_id,
            previous_mastery=current_m,
            new_mastery=new_m,
            is_correct=is_correct,
            difficulty=difficulty,
            tier=tier,
        )

    def build_adaptive_system_prompt(
        self,
        base_prompt: str,
        student_id: str,
        topic_id: str,
        course_context_text: str = "",
    ) -> str:
        """Enrich agent system prompt with mastery score, scaffolding tier, and curriculum text."""
        mastery = self.get_student_mastery(student_id, topic_id)
        tier = self.get_mastery_tier(mastery)

        if tier == "Remedial":
            scaffolding_instructions = (
                "STUDENT LEVEL: Beginner (Remedial Scaffolding)\n"
                "- The student has lower mastery on this concept (score: {mastery:.2f}).\n"
                "- Break ideas down into the simplest possible steps.\n"
                "- Use concrete everyday examples and visual metaphors.\n"
                "- Verify comprehension after each step before moving forward.\n"
                "- Never use overly dense or abstract academic jargon."
            )
        elif tier == "Core":
            scaffolding_instructions = (
                "STUDENT LEVEL: Intermediate (Core Socratic Tutoring)\n"
                "- The student has foundational understanding (score: {mastery:.2f}).\n"
                "- Use Socratic questioning to guide them to discover solutions.\n"
                "- Provide hints when they are stuck, but do not provide direct answers.\n"
                "- Ask them to explain their reasoning."
            )
        else:
            scaffolding_instructions = (
                "STUDENT LEVEL: Advanced (Mastery & Extension)\n"
                "- The student has demonstrated high mastery (score: {mastery:.2f}).\n"
                "- Be concise and direct. Skip repetitive introductory explanations.\n"
                "- Challenge them with counter-examples, edge cases, and deeper derivations.\n"
                "- Suggest advancing to the next topic in the curriculum."
            )

        prompt_parts = [
            base_prompt,
            "---",
            "ADAPTIVE PEDAGOGICAL CONTEXT:",
            scaffolding_instructions.format(mastery=mastery),
        ]

        if course_context_text:
            prompt_parts.extend([
                "---",
                "CURRICULUM TOPIC REFERENCE CONTENT:",
                course_context_text,
            ])

        return "\n\n".join(prompt_parts)


# Global singleton
bkt_mastery_engine = BKTMasteryEngine()
