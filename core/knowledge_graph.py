"""Gayatri AI — Learning Dependency Graph.

A directed graph where:
  Nodes   = learning concepts (e.g. "Python Variables", "For Loops")
  Edges   = prerequisite relationships (must know A before B)
  Node attrs = mastery score, exposure count, error count, difficulty

NOT a "mind map" (prior art US20110167329A1, WO2024215244A1).
Called a "Learning Dependency Graph" to avoid patented terminology.

Stored in SQLite. Agents query it to decide what to teach next.
No visual editor — graph is built from curriculum data and updated by agents.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.config import (
    DB_PATH,
    LDG_DECAY_RATE,
    LDG_INITIAL_MASTERY,
    LDG_LEARN_RATE,
    LDG_MASTERY_THRESHOLD,
)

logger = logging.getLogger("gayatri.ldg")


@dataclass
class Concept:
    """A single node in the Learning Dependency Graph."""
    id: str
    name: str
    description: str = ""
    difficulty: float = 0.5
    mastery: float = LDG_INITIAL_MASTERY
    exposure_count: int = 0
    error_count: int = 0
    last_practiced: str = ""
    subject: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "difficulty": self.difficulty,
            "mastery": self.mastery,
            "exposure_count": self.exposure_count,
            "error_count": self.error_count,
            "last_practiced": self.last_practiced,
            "subject": self.subject,
        }


@dataclass
class Prerequisite:
    """An edge: concept_id requires prereq_id."""
    concept_id: str
    prereq_id: str


class LearningDependencyGraph:
    """Directed graph of learning concepts with mastery tracking.

    Backed by SQLite. Thread-safe for single-user desktop use.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else Path(DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    def _conn(self) -> sqlite3.Connection:
        from core.db import get_safe_db_connection
        return get_safe_db_connection(self.db_path)

    def _create_schema(self) -> None:
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ldg_concepts (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                description     TEXT DEFAULT '',
                difficulty      REAL DEFAULT 0.5,
                mastery         REAL DEFAULT 0.3,
                exposure_count  INTEGER DEFAULT 0,
                error_count     INTEGER DEFAULT 0,
                last_practiced  TEXT DEFAULT '',
                subject         TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS ldg_prerequisites (
                concept_id  TEXT NOT NULL,
                prereq_id   TEXT NOT NULL,
                PRIMARY KEY (concept_id, prereq_id),
                FOREIGN KEY (concept_id) REFERENCES ldg_concepts(id) ON DELETE CASCADE,
                FOREIGN KEY (prereq_id)  REFERENCES ldg_concepts(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_ldg_mastery
                ON ldg_concepts(mastery);
            CREATE INDEX IF NOT EXISTS idx_ldg_subject
                ON ldg_concepts(subject);
        """)
        conn.commit()
        conn.close()

    # ── Concept CRUD ─────────────────────────────────────────────────────

    def add_concept(self, concept_id: str, name: str, description: str = "",
                    difficulty: float = 0.5, subject: str = "") -> Concept:
        """Add a new concept to the graph. Idempotent — updates if exists."""
        if difficulty < 0.0 or difficulty > 1.0:
            raise ValueError(f"Difficulty must be 0.0-1.0, got {difficulty}")

        conn = self._conn()
        conn.execute(
            """INSERT INTO ldg_concepts (id, name, description, difficulty, subject)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name = excluded.name,
                   description = excluded.description,
                   difficulty = excluded.difficulty,
                   subject = excluded.subject""",
            (concept_id, name, description, difficulty, subject),
        )
        conn.commit()
        conn.close()
        logger.info(f"Added concept: {concept_id} ({name})")
        return self.get_concept(concept_id)

    def get_concept(self, concept_id: str) -> Concept | None:
        """Get a concept by ID."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM ldg_concepts WHERE id = ?", (concept_id,)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return Concept(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            difficulty=row["difficulty"],
            mastery=row["mastery"],
            exposure_count=row["exposure_count"],
            error_count=row["error_count"],
            last_practiced=row["last_practiced"],
            subject=row["subject"],
        )

    def list_concepts(self, subject: str = "") -> list[Concept]:
        """List all concepts, optionally filtered by subject."""
        conn = self._conn()
        if subject:
            rows = conn.execute(
                "SELECT * FROM ldg_concepts WHERE subject = ? ORDER BY name", (subject,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ldg_concepts ORDER BY name").fetchall()
        conn.close()
        return [self._row_to_concept(row) for row in rows]

    def _row_to_concept(self, row: sqlite3.Row) -> Concept:
        return Concept(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            difficulty=row["difficulty"],
            mastery=row["mastery"],
            exposure_count=row["exposure_count"],
            error_count=row["error_count"],
            last_practiced=row["last_practiced"],
            subject=row["subject"],
        )

    # ── Prerequisite edges ───────────────────────────────────────────────

    def add_prerequisite(self, concept_id: str, prereq_id: str) -> None:
        """Add a prerequisite edge: concept_id requires prereq_id.

        Idempotent — safe to call multiple times.
        Validates that both concepts exist.
        """
        if concept_id == prereq_id:
            raise ValueError("Concept cannot be its own prerequisite")

        # Ensure both concepts exist
        if self.get_concept(concept_id) is None:
            raise ValueError(f"Concept not found: {concept_id}")
        if self.get_concept(prereq_id) is None:
            raise ValueError(f"Concept not found: {prereq_id}")

        # Check for cycles
        ancestors = set()
        queue = [prereq_id]
        while queue:
            current = queue.pop(0)
            if current == concept_id:
                raise ValueError(f"Adding this prerequisite would create a cycle: {concept_id} requires {prereq_id} which requires {concept_id}")
            for p in self.get_prerequisites(current):
                if p not in ancestors:
                    ancestors.add(p)
                    queue.append(p)

        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO ldg_prerequisites (concept_id, prereq_id) VALUES (?, ?)",
            (concept_id, prereq_id),
        )
        conn.commit()
        conn.close()
        logger.debug(f"Prerequisite: {concept_id} requires {prereq_id}")

    def get_prerequisites(self, concept_id: str) -> list[str]:
        """Get list of prerequisite concept IDs for a concept."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT prereq_id FROM ldg_prerequisites WHERE concept_id = ?",
            (concept_id,),
        ).fetchall()
        conn.close()
        return [row["prereq_id"] for row in rows]

    def get_dependents(self, concept_id: str) -> list[str]:
        """Get list of concept IDs that depend on this concept."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT concept_id FROM ldg_prerequisites WHERE prereq_id = ?",
            (concept_id,),
        ).fetchall()
        conn.close()
        return [row["concept_id"] for row in rows]

    # ── Mastery tracking ─────────────────────────────────────────────────

    def record_attempt(self, concept_id: str, correct: bool,
                       confidence: float = 1.0) -> float:
        """Record a student's attempt on a concept and update mastery.

        Mastery update (exponential moving average):
          correct: mastery += LEARN_RATE * (1 - mastery)
          wrong:   mastery -= DECAY_RATE * mastery

        Args:
            concept_id: The concept being attempted
            correct: Whether the student answered correctly
            confidence: How confident the assessment is (0.0-1.0)

        Returns:
            New mastery score
        """
        concept = self.get_concept(concept_id)
        if concept is None:
            raise ValueError(f"Concept not found: {concept_id}")

        if correct:
            # Learn: move mastery toward 1.0
            delta = LDG_LEARN_RATE * (1.0 - concept.mastery) * confidence
            new_mastery = min(1.0, concept.mastery + delta)
        else:
            # Decay: move mastery toward 0.0
            delta = LDG_DECAY_RATE * concept.mastery * confidence
            new_mastery = max(0.0, concept.mastery - delta)

        old_mastery = concept.mastery
        concept.mastery = new_mastery

        concept.exposure_count += 1
        if not correct:
            concept.error_count += 1
        concept.last_practiced = datetime.now().isoformat()

        # Persist
        conn = self._conn()
        conn.execute(
            """UPDATE ldg_concepts
               SET mastery = ?, exposure_count = ?, error_count = ?, last_practiced = ?
               WHERE id = ?""",
            (concept.mastery, concept.exposure_count, concept.error_count,
             concept.last_practiced, concept_id),
        )
        conn.commit()
        conn.close()

        logger.info(
            f"Attempt {concept_id}: correct={correct}, mastery={concept.mastery:.3f} "
            f"(was {old_mastery:.3f})"
        )
        return concept.mastery

    def get_mastery(self, concept_id: str) -> float:
        """Get current mastery score for a concept (0.0-1.0)."""
        concept = self.get_concept(concept_id)
        return concept.mastery if concept else 0.0

    def is_unlocked(self, concept_id: str) -> bool:
        """Check if all prerequisites are mastered (>= threshold).

        A concept is unlocked when every prerequisite has mastery >= threshold.
        If no prerequisites exist, the concept is always unlocked.
        """
        prereqs = self.get_prerequisites(concept_id)
        if not prereqs:
            return True
        return all(self.get_mastery(p) >= LDG_MASTERY_THRESHOLD for p in prereqs)

    # ── Learning path ────────────────────────────────────────────────────

    def get_next_concept(self, subject: str = "") -> Concept | None:
        """Get the next concept to teach.

        Selection criteria (in priority order):
          1. Unlocked (all prereqs mastered)
          2. Lowest mastery among unlocked concepts
          3. Lowest difficulty (easier to start)
          4. Least recently practiced

        Args:
            subject: Optional subject filter

        Returns:
            The best next concept, or None if graph is empty
        """
        candidates = self.list_concepts(subject=subject)
        if not candidates:
            return None

        unlocked = [c for c in candidates if self.is_unlocked(c.id)]
        if not unlocked:
            # Nothing unlocked — find the concept whose prereqs are closest to mastery
            logger.warning("No concepts unlocked — all prerequisites not yet mastered")
            return None

        # Sort: lowest mastery first, then lowest difficulty, then oldest practice
        unlocked.sort(key=lambda c: (
            c.mastery,
            c.difficulty,
            -(c.exposure_count),  # prefer concepts not yet practiced
        ))
        return unlocked[0]

    def get_learning_path(self, goal_concept: str) -> list[Concept]:
        """Get the full learning path from roots to a goal concept.

        Uses topological sort on prerequisite edges.
        Returns concepts in the order they should be learned.

        Args:
            goal_concept: Target concept ID

        Returns:
            Ordered list of concepts from prerequisites to goal
        """
        # Build adjacency: prereq → [dependents]
        all_concepts = {c.id: c for c in self.list_concepts()}
        if goal_concept not in all_concepts:
            return []

        # Topological sort (Kahn's algorithm) limited to ancestors of goal
        # Collect all ancestors of goal
        ancestors = set()
        queue = [goal_concept]
        while queue:
            current = queue.pop(0)
            prereqs = self.get_prerequisites(current)
            for p in prereqs:
                if p not in ancestors:
                    ancestors.add(p)
                    queue.append(p)

        # Sort ancestors by dependency order (no cycles in valid curriculum)
        # Kahn's algorithm on the subgraph
        in_degree = {cid: 0 for cid in ancestors}
        dependents: dict[str, list[str]] = {cid: [] for cid in ancestors}

        for cid in ancestors:
            for prereq in self.get_prerequisites(cid):
                if prereq in ancestors:
                    in_degree[cid] = in_degree.get(cid, 0) + 1
                    dependents[prereq].append(cid)

        # BFS topological sort
        queue = [cid for cid in ancestors if in_degree[cid] == 0]
        sorted_ancestors = []
        while queue:
            queue.sort()  # deterministic order
            node = queue.pop(0)
            sorted_ancestors.append(node)
            for dep in dependents.get(node, []):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        # Add the goal concept at the end if not already included
        if goal_concept not in sorted_ancestors:
            sorted_ancestors.append(goal_concept)

        return [all_concepts[cid] for cid in sorted_ancestors if cid in all_concepts]

    def get_weak_concepts(self, top_n: int = 5, subject: str = "") -> list[Concept]:
        """Get the concepts with lowest mastery scores.

        Useful for targeted practice and review.
        """
        concepts = self.list_concepts(subject=subject)
        # Sort by mastery ascending, then by exposure (less practiced = more urgent)
        concepts.sort(key=lambda c: (c.mastery, c.exposure_count))
        return concepts[:top_n]

    def get_mastered_concepts(self, subject: str = "") -> list[Concept]:
        """Get concepts where mastery >= threshold."""
        concepts = self.list_concepts(subject=subject)
        return [c for c in concepts if c.mastery >= LDG_MASTERY_THRESHOLD]

    def get_concepts_in_progress(self, subject: str = "") -> list[Concept]:
        """Get concepts with 0 < mastery < threshold."""
        concepts = self.list_concepts(subject=subject)
        return [c for c in concepts if 0.0 < c.mastery < LDG_MASTERY_THRESHOLD]

    def get_not_started_concepts(self, subject: str = "") -> list[Concept]:
        """Get concepts with mastery == initial (never attempted)."""
        concepts = self.list_concepts(subject=subject)
        return [c for c in concepts if c.mastery <= LDG_INITIAL_MASTERY + 0.01]

    def get_progress_stats(self, subject: str = "") -> dict:
        """Get overall progress statistics for a subject."""
        concepts = self.list_concepts(subject=subject)
        if not concepts:
            return {"total": 0, "mastered": 0, "in_progress": 0, "not_started": 0,
                    "avg_mastery": 0.0}

        mastered = sum(1 for c in concepts if c.mastery >= LDG_MASTERY_THRESHOLD)
        in_progress = sum(1 for c in concepts if 0.0 < c.mastery < LDG_MASTERY_THRESHOLD)
        not_started = sum(1 for c in concepts if c.mastery <= LDG_INITIAL_MASTERY + 0.01)
        avg_mastery = sum(c.mastery for c in concepts) / len(concepts)

        return {
            "total": len(concepts),
            "mastered": mastered,
            "in_progress": in_progress,
            "not_started": not_started,
            "avg_mastery": round(avg_mastery, 3),
            "mastery_pct": round(avg_mastery * 100, 1),
        }

    def reset_concept(self, concept_id: str) -> None:
        """Reset a concept to initial mastery (for retrying)."""
        conn = self._conn()
        conn.execute(
            """UPDATE ldg_concepts
               SET mastery = ?, exposure_count = 0, error_count = 0, last_practiced = ''
               WHERE id = ?""",
            (LDG_INITIAL_MASTERY, concept_id),
        )
        conn.commit()
        conn.close()
        logger.info(f"Reset concept: {concept_id}")

    def reset_all(self) -> None:
        """Reset all concepts to initial mastery. Use with caution."""
        conn = self._conn()
        conn.execute(
            """UPDATE ldg_concepts
               SET mastery = ?, exposure_count = 0, error_count = 0, last_practiced = ''
            """,
            (LDG_INITIAL_MASTERY,),
        )
        conn.commit()
        conn.close()
        logger.warning("All concepts reset to initial mastery")

    def delete_concept(self, concept_id: str) -> None:
        """Remove a concept and its prerequisite edges."""
        conn = self._conn()
        conn.execute("DELETE FROM ldg_prerequisites WHERE concept_id = ? OR prereq_id = ?",
                     (concept_id, concept_id))
        conn.execute("DELETE FROM ldg_concepts WHERE id = ?", (concept_id,))
        conn.commit()
        conn.close()
        logger.info(f"Deleted concept: {concept_id}")


# ── Curriculum loader ────────────────────────────────────────────────────

def load_curriculum(graph: LearningDependencyGraph, curriculum_path: str | Path) -> int:
    """Load a curriculum JSON file into the graph.

    Args:
        graph: The LDG instance to populate
        curriculum_path: Path to a JSON file with curriculum data

    Returns:
        Number of concepts loaded
    """
    import json
    path = Path(curriculum_path)
    if not path.exists():
        raise FileNotFoundError(f"Curriculum file not found: {path}")

    with open(path) as f:
        data = json.load(f)

    concepts_added = 0
    for concept_data in data.get("concepts", []):
        graph.add_concept(
            concept_id=concept_data["id"],
            name=concept_data["name"],
            description=concept_data.get("description", ""),
            difficulty=concept_data.get("difficulty", 0.5),
            subject=data.get("subject", ""),
        )
        concepts_added += 1

    # Add prerequisite edges (after all concepts exist)
    for concept_data in data.get("concepts", []):
        concept_id = concept_data["id"]
        for prereq_id in concept_data.get("prerequisites", []):
            graph.add_prerequisite(concept_id, prereq_id)

    subject_label = data.get("subject", "unknown")
    logger.info(f"Loaded curriculum '{subject_label}': {concepts_added} concepts")
    return concepts_added
