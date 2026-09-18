"""Course-as-Markdown Parser & Ingestion Engine.

Parses structured Markdown curriculum files according to the K-12 spec:
- YAML frontmatter with course_id, subject, grade, title, topics list
- Heading anchors {#topic-id} mapping to sub-topics
- Inline level:N difficulty markers for paragraphs
- Fenced ```quiz blocks containing machine-parseable placement & practice questions
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger("gayatri.tutor.course_loader")


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Lightweight zero-dependency parser for course frontmatter and quiz blocks.

    Handles key: value scalars, lists (- item), and nested lists of dicts.
    """
    if yaml is not None:
        try:
            return yaml.safe_load(text) or {}
        except Exception:
            pass

    result: dict[str, Any] = {}
    lines = text.splitlines()
    current_list_key: str | None = None
    current_dict_item: dict[str, Any] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Handle list item under a list key
        if line.startswith("  - ") or line.startswith("    - ") or stripped.startswith("- "):
            item_str = stripped.lstrip("- ").strip()
            if ":" in item_str:
                k, v = item_str.split(":", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                current_dict_item = {k: v}
                if current_list_key and isinstance(result.get(current_list_key), list):
                    result[current_list_key].append(current_dict_item)
            else:
                val = item_str.strip("\"'")
                if current_list_key and isinstance(result.get(current_list_key), list):
                    result[current_list_key].append(val)
            continue

        # Handle sub-key under current dict item in a list (e.g. title: "What is a Fraction?")
        if (line.startswith("    ") or line.startswith("      ")) and current_dict_item is not None and ":" in stripped:
            k, v = stripped.split(":", 1)
            current_dict_item[k.strip()] = v.strip().strip("\"'")
            continue

        # Handle top-level key: value or key: [list]
        if ":" in stripped:
            k, v = stripped.split(":", 1)
            k = k.strip()
            v = v.strip()

            if v.startswith("[") and v.endswith("]"):
                # JSON/Python inline list: ["a", "b"]
                inner = v[1:-1].strip()
                items = [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]
                result[k] = items
                current_list_key = None
                current_dict_item = None
            elif not v:
                # Key starting a multi-line list
                result[k] = []
                current_list_key = k
                current_dict_item = None
            else:
                clean_v = v.strip("\"'")
                if clean_v.isdigit():
                    result[k] = int(clean_v)
                else:
                    result[k] = clean_v
                current_list_key = None
                current_dict_item = None

    return result


@dataclass
class ParsedQuizQuestion:
    """Represents a quiz or practice question parsed from a markdown ```quiz block."""
    id: str
    topic_id: str
    type: str  # mcq | short
    difficulty: int  # 1 to 5 scale
    question: str
    options: list[str] = field(default_factory=list)
    answer: int = 0  # 0-indexed correct option index
    explanation: str = ""


@dataclass
class ParsedTopic:
    """Represents a topic within a course, parsed from heading anchors and content."""
    id: str
    title: str
    anchor: str
    order: int
    content_by_level: dict[int, list[str]] = field(default_factory=lambda: {1: [], 2: [], 3: [], 4: [], 5: []})
    general_content: list[str] = field(default_factory=list)
    questions: list[ParsedQuizQuestion] = field(default_factory=list)

    def get_content_for_difficulty(self, difficulty: int) -> str:
        """Retrieve appropriate content for a given difficulty level (1-5)."""
        clamped_diff = max(1, min(5, difficulty))
        matched = self.content_by_level.get(clamped_diff, [])
        if matched:
            return "\n\n".join(matched)
        # Fallback to general content or closest level
        if self.general_content:
            return "\n\n".join(self.general_content)
        for d in (clamped_diff - 1, clamped_diff + 1, 1, 2, 3, 4, 5):
            if self.content_by_level.get(d):
                return "\n\n".join(self.content_by_level[d])
        return ""


@dataclass
class ParsedCourse:
    """Represents a complete course parsed from a single markdown file."""
    course_id: str
    subject: str
    grade: int
    title: str
    difficulty_default: int = 2
    topics: list[ParsedTopic] = field(default_factory=list)
    source_file: str = ""

    def get_topic(self, topic_id: str) -> ParsedTopic | None:
        for t in self.topics:
            if t.id == topic_id:
                return t
        return None

    def all_questions(self) -> list[ParsedQuizQuestion]:
        all_q = []
        for t in self.topics:
            all_q.extend(t.questions)
        return all_q


class CourseLoader:
    """Parser that transforms Course-as-Markdown files into structured in-memory objects."""

    @staticmethod
    def load_from_file(file_path: str | Path) -> ParsedCourse:
        """Read and parse a .md course file from the filesystem."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Course file not found: {path}")

        raw_text = path.read_text(encoding="utf-8")
        course = CourseLoader.parse_markdown_string(raw_text)
        course.source_file = str(path)
        return course

    @staticmethod
    def parse_markdown_string(text: str) -> ParsedCourse:
        """Parse raw markdown content containing frontmatter, anchors, and quiz blocks."""
        frontmatter_data: dict[str, Any] = {}
        body_text = text

        # 1. Parse YAML Frontmatter
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if frontmatter_match:
            raw_yaml = frontmatter_match.group(1)
            try:
                frontmatter_data = _parse_simple_yaml(raw_yaml)
            except Exception as e:
                logger.warning(f"Error parsing course YAML frontmatter: {e}")
            body_text = text[frontmatter_match.end():]

        course_id = frontmatter_data.get("course_id", "course-untitled")
        subject = frontmatter_data.get("subject", "General")
        grade = int(frontmatter_data.get("grade", 1))
        title = frontmatter_data.get("title", "Untitled Course")
        difficulty_default = int(frontmatter_data.get("difficulty_default", 2))

        declared_topics = frontmatter_data.get("topics", [])
        declared_topic_map = {t.get("id"): t.get("title") for t in declared_topics if isinstance(t, dict)}

        # 2. Split body into topic sections based on headings with anchors: # Heading {#anchor}
        heading_pattern = re.compile(r"^(#{1,3})\s+(.*?)\s+\{#([\w\-]+)\}\s*$", re.MULTILINE)
        matches = list(heading_pattern.finditer(body_text))

        parsed_topics: list[ParsedTopic] = []

        if not matches:
            # Entire file is one default topic
            default_topic_id = list(declared_topic_map.keys())[0] if declared_topic_map else "topic-1"
            default_title = declared_topic_map.get(default_topic_id, title)
            topic = CourseLoader._parse_topic_content(default_topic_id, default_title, default_topic_id, 1, body_text)
            parsed_topics.append(topic)
        else:
            for idx, match in enumerate(matches):
                level_str, heading_title, anchor_id = match.groups()
                start_pos = match.end()
                end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(body_text)
                section_content = body_text[start_pos:end_pos].strip()

                final_title = declared_topic_map.get(anchor_id, heading_title.strip())
                topic = CourseLoader._parse_topic_content(anchor_id, final_title, anchor_id, idx + 1, section_content)
                parsed_topics.append(topic)

        return ParsedCourse(
            course_id=course_id,
            subject=subject,
            grade=grade,
            title=title,
            difficulty_default=difficulty_default,
            topics=parsed_topics,
        )

    @staticmethod
    def _parse_topic_content(topic_id: str, title: str, anchor: str, order: int, raw_section: str) -> ParsedTopic:
        """Parse paragraph levels and ```quiz blocks inside a topic section."""
        topic = ParsedTopic(id=topic_id, title=title, anchor=anchor, order=order)

        # 1. Extract ```quiz blocks
        quiz_block_pattern = re.compile(r"```quiz\s*\n(.*?)\n```", re.DOTALL)
        for quiz_match in quiz_block_pattern.finditer(raw_section):
            yaml_quiz_str = quiz_match.group(1)
            try:
                q_data = _parse_simple_yaml(yaml_quiz_str)
                if isinstance(q_data, dict):
                    question_obj = ParsedQuizQuestion(
                        id=str(q_data.get("id", f"{topic_id}-q{len(topic.questions) + 1}")),
                        topic_id=topic_id,
                        type=str(q_data.get("type", "mcq")),
                        difficulty=int(q_data.get("difficulty", 2)),
                        question=str(q_data.get("question", "")).strip(),
                        options=[str(opt) for opt in q_data.get("options", [])],
                        answer=int(q_data.get("answer", 0)),
                        explanation=str(q_data.get("explanation", "")).strip(),
                    )
                    topic.questions.append(question_obj)
            except Exception as e:
                logger.warning(f"Failed to parse quiz block in topic {topic_id}: {e}")

        # Remove ```quiz blocks from text before parsing narrative paragraphs
        text_without_quiz = quiz_block_pattern.sub("", raw_section)

        # 2. Parse narrative paragraphs and level:N markers
        paragraphs = [p.strip() for p in text_without_quiz.split("\n\n") if p.strip()]
        level_marker_pattern = re.compile(r"<!--\s*level:([1-5])\s*-->|\[level:([1-5])\]|^`level:([1-5])`", re.IGNORECASE)

        for paragraph in paragraphs:
            marker_match = level_marker_pattern.search(paragraph)
            if marker_match:
                diff_level = int(next(filter(None, marker_match.groups())))
                cleaned_paragraph = level_marker_pattern.sub("", paragraph).strip()
                topic.content_by_level[diff_level].append(cleaned_paragraph)
            else:
                topic.general_content.append(paragraph)

        return topic
