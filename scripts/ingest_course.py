"""Gayatri AI — Course Ingestion & Validation CLI (Sec 9 & 10).

Ingests Course-as-Markdown (.md) curriculum files into the SQLite database.
Validates YAML frontmatter, heading anchors, difficulty levels, and quiz blocks.

Usage:
    python scripts/ingest_course.py content/courses/math_g5_fractions.md
    python scripts/ingest_course.py content/courses/
    python scripts/ingest_course.py content/courses/ --validate-only
    python scripts/ingest_course.py content/courses/ --watch
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.tutor.course_loader import CourseLoader, ParsedCourse
from core.tutor.course_repo import course_repo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_course")


def validate_course(course: ParsedCourse) -> list[str]:
    """Validate parsed course for schema compliance and pedagogical integrity.

    Returns a list of error strings (empty if valid).
    """
    errors: list[str] = []

    if not course.course_id or course.course_id == "course-untitled":
        errors.append("Missing or invalid 'course_id' in frontmatter.")

    if not course.subject:
        errors.append("Missing 'subject' in frontmatter.")

    if course.grade < 1 or course.grade > 12:
        errors.append(f"Invalid grade {course.grade}: must be between 1 and 12.")

    if not course.topics:
        errors.append("No topics found in course. Ensure headings have {#topic-id} anchors.")

    for topic in course.topics:
        if not topic.id:
            errors.append(f"Topic with title '{topic.title}' lacks a valid anchor ID.")

        for q in topic.questions:
            if not q.question:
                errors.append(f"Topic '{topic.id}' has a quiz question with empty question text.")
            if q.type == "mcq":
                if len(q.options) < 2:
                    errors.append(f"Quiz question '{q.id}' in '{topic.id}' must have at least 2 options.")
                if q.answer < 0 or q.answer >= len(q.options):
                    errors.append(
                        f"Quiz question '{q.id}' in '{topic.id}' has out-of-bounds answer index {q.answer} "
                        f"(options count: {len(q.options)})."
                    )
            if q.difficulty < 1 or q.difficulty > 5:
                errors.append(f"Quiz question '{q.id}' has difficulty {q.difficulty}, must be 1-5.")

    return errors


def ingest_file(file_path: Path, validate_only: bool = False) -> bool:
    """Ingest a single .md course file."""
    if not file_path.is_file() or file_path.suffix.lower() != ".md":
        return False

    try:
        course = CourseLoader.load_from_file(file_path)
    except Exception as exc:
        logger.error(f"Failed to read/parse {file_path.name}: {exc}")
        return False

    errors = validate_course(course)
    if errors:
        logger.error(f"Validation FAILED for {file_path.name} ({len(errors)} errors):")
        for err in errors:
            logger.error(f"  • {err}")
        return False

    all_qs = course.all_questions()
    if validate_only:
        logger.info(
            f"✓ VALID: {file_path.name} — '{course.title}' (Grade {course.grade} {course.subject}) | "
            f"{len(course.topics)} topics, {len(all_qs)} questions"
        )
        return True

    course_repo.save_course(course)
    logger.info(
        f"✓ INGESTED: {file_path.name} -> DB (ID: {course.course_id}) | "
        f"{len(course.topics)} topics, {len(all_qs)} questions"
    )
    for t in course.topics:
        logger.info(f"    - Topic [{t.id}]: '{t.title}' ({len(t.questions)} quiz questions)")
    return True


def ingest_path(target_path: Path, validate_only: bool = False) -> int:
    """Ingest a file or all .md files in a directory. Returns count of successfully ingested courses."""
    if target_path.is_file():
        success = ingest_file(target_path, validate_only=validate_only)
        return 1 if success else 0

    if not target_path.is_dir():
        logger.error(f"Path not found: {target_path}")
        return 0

    md_files = sorted(target_path.glob("*.md"))
    if not md_files:
        logger.warning(f"No .md files found in {target_path}")
        return 0

    count = 0
    for md_file in md_files:
        if ingest_file(md_file, validate_only=validate_only):
            count += 1
    return count


def watch_directory(dir_path: Path, interval_sec: float = 3.0):
    """Continuously watch a directory and auto-ingest modified or new .md files."""
    logger.info(f"Watching {dir_path.resolve()} for course changes (polling every {interval_sec}s)...")
    logger.info("Press Ctrl+C to stop.")
    mtimes: dict[Path, float] = {}

    try:
        while True:
            for p in dir_path.glob("*.md"):
                cur_mtime = p.stat().st_mtime
                prev_mtime = mtimes.get(p)
                if prev_mtime is None or cur_mtime > prev_mtime:
                    mtimes[p] = cur_mtime
                    action = "New file detected" if prev_mtime is None else "Change detected"
                    logger.info(f"{action}: {p.name} — ingesting...")
                    ingest_file(p, validate_only=False)
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        logger.info("Watch stopped.")


def main():
    parser = argparse.ArgumentParser(description="Ingest and validate Course-as-Markdown files into Gayatri Tutor DB.")
    parser.add_argument("path", type=str, nargs="?", default="content/courses/", help="Path to .md file or directory")
    parser.add_argument("--validate-only", action="store_true", help="Validate schema and lint without writing to DB")
    parser.add_argument("--watch", action="store_true", help="Watch directory for changes and auto-ingest")

    args = parser.parse_args()
    target = Path(args.path)

    if args.watch:
        if not target.is_dir():
            target = target.parent
        watch_directory(target)
    else:
        logger.info(f"Scanning target: {target.resolve()}")
        successful = ingest_path(target, validate_only=args.validate_only)
        mode = "validated" if args.validate_only else "ingested"
        logger.info(f"Finished: {successful} course file(s) successfully {mode}.")


if __name__ == "__main__":
    main()
