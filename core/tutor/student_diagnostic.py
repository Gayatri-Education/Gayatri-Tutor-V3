"""Student Diagnostic Assessment System.

Provides baseline placement testing for K-12 students:
- Selects 5-8 questions across difficulty levels 1 through 5
- Computes baseline mastery M0 = sum(correct_i * difficulty_i) / sum(difficulty_i)
- Records attempts and seeds initial mastery in the repository
- Generates pedagogical placement reports and recommendations
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

from core.tutor.course_repo import CourseRepository, course_repo

logger = logging.getLogger("gayatri.tutor.diagnostic")


@dataclass
class DiagnosticSubmission:
    question_id: str
    selected_option_index: int
    response_time_ms: int = 0


@dataclass
class DiagnosticResult:
    topic_id: str
    student_id: str
    total_questions: int
    correct_count: int
    initial_mastery: float
    mastery_tier: str  # "Remedial" | "Core" | "Advanced"
    question_results: list[dict[str, Any]] = field(default_factory=list)
    recommendation: str = ""


class StudentDiagnosticEngine:
    """Selects and scores diagnostic placement assessments for topics."""

    def __init__(self, repo: CourseRepository | None = None):
        self.repo = repo or course_repo

    def select_diagnostic_quiz(
        self,
        topic_id: str,
        min_questions: int = 3,
        max_questions: int = 8,
    ) -> list[dict[str, Any]]:
        """Select a balanced set of diagnostic questions spanning difficulties 1 to 5."""
        all_questions = self.repo.get_questions_for_topic(topic_id)
        if not all_questions:
            logger.warning(f"No questions found for topic '{topic_id}' to generate diagnostic.")
            return []

        # Group by difficulty level
        by_diff: dict[int, list[dict[str, Any]]] = {1: [], 2: [], 3: [], 4: [], 5: []}
        for q in all_questions:
            d = max(1, min(5, q.get("difficulty", 2)))
            by_diff[d].append(q)

        selected: list[dict[str, Any]] = []

        # 1. First pass: Pick 1 question from each available difficulty tier (1 -> 5)
        for diff in range(1, 6):
            if by_diff[diff]:
                chosen = random.choice(by_diff[diff])
                selected.append(chosen)

        # 2. Second pass: Fill up to min_questions or max_questions from remaining pool
        remaining = [q for q in all_questions if q["id"] not in {s["id"] for s in selected}]
        random.shuffle(remaining)

        while len(selected) < min_questions and remaining:
            selected.append(remaining.pop(0))

        while len(selected) < max_questions and remaining:
            selected.append(remaining.pop(0))

        # Sort selected by difficulty ascending for smooth student experience
        selected.sort(key=lambda q: (q.get("difficulty", 2), q.get("id")))

        # Sanitize output: remove correct answer index before serving to student UI
        sanitized = []
        for q in selected:
            sanitized.append({
                "id": q["id"],
                "topic_id": q["topic_id"],
                "difficulty": q["difficulty"],
                "type": q["type"],
                "question": q["question"],
                "options": q["options"],
            })

        return sanitized

    def evaluate_diagnostic(
        self,
        student_id: str,
        topic_id: str,
        submissions: list[DiagnosticSubmission],
    ) -> DiagnosticResult:
        """Score diagnostic submissions, seed topic mastery, and log attempts."""
        all_topic_questions = {q["id"]: q for q in self.repo.get_questions_for_topic(topic_id)}

        total_weight = 0.0
        weighted_score = 0.0
        correct_count = 0
        detailed_results = []

        for sub in submissions:
            q = all_topic_questions.get(sub.question_id)
            if not q:
                continue

            diff = max(1, min(5, q.get("difficulty", 2)))
            correct_answer = q.get("answer_index", 0)
            is_correct = (sub.selected_option_index == correct_answer)

            if is_correct:
                correct_count += 1
                weighted_score += float(diff)

            total_weight += float(diff)

            # Record attempt in database
            self.repo.record_attempt(
                student_id=student_id,
                topic_id=topic_id,
                question_id=sub.question_id,
                is_correct=is_correct,
                response_time_ms=sub.response_time_ms,
            )

            detailed_results.append({
                "question_id": sub.question_id,
                "question": q["question"],
                "difficulty": diff,
                "selected_option": sub.selected_option_index,
                "correct_option": correct_answer,
                "is_correct": is_correct,
                "explanation": q.get("explanation", ""),
            })

        # Calculate M0 = sum(correct * diff) / sum(diff)
        if total_weight > 0:
            initial_mastery = round(weighted_score / total_weight, 3)
        else:
            initial_mastery = 0.30  # Default prior

        # Assign pedagogical tier
        if initial_mastery < 0.40:
            tier = "Remedial"
            recommendation = (
                "Student is at the foundation stage. The tutor will provide high-scaffolding explanations, "
                "visual analogies, and step-by-step guidance."
            )
        elif initial_mastery < 0.70:
            tier = "Core"
            recommendation = (
                "Student shows good basic comprehension. The tutor will use active Socratic dialogue "
                "to deepen conceptual intuition."
            )
        else:
            tier = "Advanced"
            recommendation = (
                "Student demonstrates high baseline mastery. The tutor will present challenging edge-cases "
                "and prepare for rapid concept completion."
            )

        # Persist initial mastery
        self.repo.set_mastery(
            student_id=student_id,
            topic_id=topic_id,
            mastery_score=initial_mastery,
            confidence=0.75,
        )

        # Log completion event
        self.repo.log_event(
            student_id=student_id,
            topic_id=topic_id,
            event_type="diagnostic_completed",
            payload={
                "initial_mastery": initial_mastery,
                "tier": tier,
                "correct_count": correct_count,
                "total_questions": len(submissions),
            },
        )

        return DiagnosticResult(
            topic_id=topic_id,
            student_id=student_id,
            total_questions=len(submissions),
            correct_count=correct_count,
            initial_mastery=initial_mastery,
            mastery_tier=tier,
            question_results=detailed_results,
            recommendation=recommendation,
        )


# Global singleton
diagnostic_engine = StudentDiagnosticEngine()
