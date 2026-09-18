"""Automated Behavioral and Unit Tests for K-12 Adaptive Tutor Features.

Verifies:
- 21 K-12 Agents registration and command routing
- CourseLoader markdown parsing (frontmatter, anchors, levels, quiz blocks)
- CourseRepository SQLite persistence
- StudentDiagnosticEngine question selection and baseline placement
- BKTMasteryEngine mathematical convergence and bounds
- Adaptive prompt scaffolding injection
"""

import pytest

from core.agents.registry import agent_registry
from core.tutor.course_loader import CourseLoader, ParsedCourse
from core.tutor.course_repo import CourseRepository
from core.tutor.mastery_engine import BKTMasteryEngine
from core.tutor.student_diagnostic import DiagnosticSubmission, StudentDiagnosticEngine


def test_k12_agents_registered():
    """Verify key K-12 agents are registered with expected commands."""
    expected_k12_agents = [
        ("Elementary Math Tutor", "/elem-math"),
        ("Algebra Tutor", "/algebra"),
        ("Geometry Tutor", "/geometry"),
        ("Physics Tutor", "/physics"),
        ("Chemistry Tutor", "/chemistry"),
        ("Biology Tutor", "/biology"),
        ("Environmental Science Tutor", "/evs"),
        ("History & Civics Tutor", "/history"),
        ("Geography Tutor", "/geography"),
        ("English Grammar Coach", "/grammar"),
        ("Reading Comprehension Coach", "/comprehend"),
        ("Creative Writing Mentor", "/write-story"),
        ("Primary School Coach", "/primary"),
        ("Middle School Mentor", "/middle"),
        ("High School & Exam Coach", "/senior"),
        ("Socratic Questioner", "/socratic"),
        ("Progressive Hint Giver", "/hint"),
        ("Doubt Buster", "/doubt"),
        ("Formula & Theorem Companion", "/formula"),
        ("Quiz Master", "/quizmaster"),
        ("Study Habit Coach", "/study-coach"),
    ]

    for name, cmd in expected_k12_agents:
        spec = agent_registry.get(name)
        assert spec is not None, f"Agent '{name}' is not registered"
        assert cmd in spec.commands, f"Command '{cmd}' not found for agent '{name}'"


def test_course_loader_parsing():
    """Verify CourseLoader parses YAML frontmatter, anchors, and quiz blocks."""
    raw_md = """---
course_id: test-course
subject: Mathematics
grade: 4
title: "Test Math Course"
difficulty_default: 2
topics:
  - id: topic-a
    title: "Topic A"
---

# Topic A {#topic-a}

`level:1`
Level 1 intro paragraph.

`level:4`
Level 4 advanced paragraph.

```quiz
id: test-q1
type: mcq
difficulty: 2
question: "What is 2 + 2?"
options: ["3", "4", "5"]
answer: 1
explanation: "2 + 2 = 4"
```
"""
    course = CourseLoader.parse_markdown_string(raw_md)
    assert course.course_id == "test-course"
    assert course.subject == "Mathematics"
    assert course.grade == 4
    assert len(course.topics) == 1

    topic = course.topics[0]
    assert topic.id == "topic-a"
    assert topic.title == "Topic A"
    assert len(topic.questions) == 1

    q = topic.questions[0]
    assert q.id == "test-q1"
    assert q.difficulty == 2
    assert q.answer == 1
    assert q.options == ["3", "4", "5"]

    # Verify content filtering by level
    lvl1_content = topic.get_content_for_difficulty(1)
    assert "Level 1 intro paragraph." in lvl1_content


def test_course_repo_in_memory():
    """Verify CourseRepository saves and retrieves in an isolated in-memory DB."""
    repo = CourseRepository(db_path=":memory:")

    # Load and save pilot course
    course = CourseLoader.load_from_file("content/courses/math_g5_fractions.md")
    repo.save_course(course)

    courses = repo.list_courses()
    assert len(courses) == 1
    assert courses[0]["id"] == "math-g5-fractions"

    topics = repo.get_topics_for_course("math-g5-fractions")
    assert len(topics) == 3

    questions = repo.get_questions_for_topic("frac-basics")
    assert len(questions) == 3


def test_student_diagnostic_scoring():
    """Verify placement test question selection, scoring, and initial seeding."""
    repo = CourseRepository(db_path=":memory:")
    course = CourseLoader.load_from_file("content/courses/math_g5_fractions.md")
    repo.save_course(course)

    diagnostic = StudentDiagnosticEngine(repo=repo)
    quiz = diagnostic.select_diagnostic_quiz("frac-basics")
    assert len(quiz) >= 1

    # Simulate answering all correctly
    all_correct_subs = []
    for q in quiz:
        # Fetch actual answer to answer correctly
        full_q = [x for x in repo.get_questions_for_topic("frac-basics") if x["id"] == q["id"]][0]
        all_correct_subs.append(DiagnosticSubmission(q["id"], full_q["answer_index"]))

    res = diagnostic.evaluate_diagnostic("student-test", "frac-basics", all_correct_subs)
    assert res.correct_count == len(quiz)
    assert res.initial_mastery == 1.0
    assert res.mastery_tier == "Advanced"

    # Verify stored in repository
    mastery_record = repo.get_mastery("student-test", "frac-basics")
    assert mastery_record is not None
    assert mastery_record["mastery_score"] == 1.0


def test_bkt_mastery_engine():
    """Verify BKT updates correctly scale with difficulty and respect bounds [0.0, 1.0]."""
    repo = CourseRepository(db_path=":memory:")
    engine = BKTMasteryEngine(repo=repo, learning_rate=0.2)

    # Initial prior
    m0 = engine.get_student_mastery("student-1", "topic-1")
    assert m0 == 0.30

    # Correct answer increases mastery
    res1 = engine.update_mastery("student-1", "topic-1", is_correct=True, difficulty=3)
    assert res1.new_mastery > m0
    assert res1.tier in ("Remedial", "Core", "Advanced")

    # Incorrect answer decreases mastery
    res2 = engine.update_mastery("student-1", "topic-1", is_correct=False, difficulty=2)
    assert res2.new_mastery < res1.new_mastery

    # Upper bound test: consecutive correct answers cannot exceed 1.0
    for _ in range(30):
        engine.update_mastery("student-1", "topic-1", is_correct=True, difficulty=5)
    assert engine.get_student_mastery("student-1", "topic-1") <= 1.0

    # Lower bound test: consecutive wrong answers cannot fall below 0.0
    for _ in range(30):
        engine.update_mastery("student-1", "topic-1", is_correct=False, difficulty=5)
    assert engine.get_student_mastery("student-1", "topic-1") >= 0.0


def test_adaptive_prompt_tiers():
    """Verify adaptive system prompt correctly reflects beginner, core, and advanced levels."""
    repo = CourseRepository(db_path=":memory:")
    engine = BKTMasteryEngine(repo=repo)

    # Remedial tier
    repo.set_mastery("st-rem", "topic-1", mastery_score=0.20)
    p_rem = engine.build_adaptive_system_prompt("Base", "st-rem", "topic-1")
    assert "Remedial Scaffolding" in p_rem

    # Core tier
    repo.set_mastery("st-core", "topic-1", mastery_score=0.55)
    p_core = engine.build_adaptive_system_prompt("Base", "st-core", "topic-1")
    assert "Core Socratic Tutoring" in p_core

    # Advanced tier
    repo.set_mastery("st-adv", "topic-1", mastery_score=0.85)
    p_adv = engine.build_adaptive_system_prompt("Base", "st-adv", "topic-1")
    assert "Mastery & Extension" in p_adv


def test_cli_ingest_course_validation(tmp_path):
    """Verify scripts/ingest_course.py validation logic and ingestion."""
    from scripts.ingest_course import validate_course, ingest_file

    # 1. Invalid course (missing subject, bad grade, no topics)
    bad_course = ParsedCourse(
        course_id="bad-1",
        title="Bad",
        subject="",
        grade=15,
        topics=[],
    )
    errors = validate_course(bad_course)
    assert len(errors) >= 3

    # 2. Valid course file
    valid_md = """---
course_id: test-cli-course
subject: Mathematics
grade: 6
title: "CLI Ingest Test Course"
---
# Fractions {#cli-fractions}
Introduction to fractions.

```quiz
type: mcq
difficulty: 2
question: What is 1/2 + 1/2?
options:
  - "1/4"
  - "1"
  - "2"
answer: 1
explanation: Half plus half equals one.
```
"""
    test_file = tmp_path / "test_course.md"
    test_file.write_text(valid_md, encoding="utf-8")

    # Ingest in validate-only mode
    assert ingest_file(test_file, validate_only=True) is True

    # Ingest to DB
    assert ingest_file(test_file, validate_only=False) is True


def test_nightly_mastery_report_generation(tmp_path):
    """Verify scripts/nightly_mastery_report.py aggregates stats and outputs CSV/JSON."""
    from scripts.nightly_mastery_report import generate_mastery_summary, export_reports
    from core.tutor.course_repo import course_repo

    # Seed test student mastery and diagnostic attempt
    course_repo.set_mastery("test_student_report", "cli-fractions", mastery_score=0.85)
    course_repo.record_attempt(
        student_id="test_student_report",
        topic_id="cli-fractions",
        question_id="q-cli-1",
        is_correct=True,
        response_time_ms=1200,
    )

    summary = generate_mastery_summary("test_student_report")
    assert summary["total_records"] >= 1
    assert "test_student_report" in summary["students"]

    student_data = summary["students"]["test_student_report"]
    assert student_data["topics_mastered"] >= 1
    assert student_data["total_attempts"] >= 1

    # Export to temp directory
    json_path, csv_path = export_reports(summary, tmp_path)
    assert json_path.exists()
    assert csv_path.exists()
    assert json_path.stat().st_size > 0
    assert csv_path.stat().st_size > 0


def test_bridge_k12_slots():
    """Verify Bridge slots for K-12 course browsing and diagnostic quiz."""
    import json
    from app.bridge.facade import Bridge

    bridge = Bridge()

    # 1. get_k12_courses
    courses_json = bridge.get_k12_courses()
    courses = json.loads(courses_json)
    assert isinstance(courses, list)

    # 2. get_k12_topics
    topics_json = bridge.get_k12_topics("test-cli-course")
    topics = json.loads(topics_json)
    assert isinstance(topics, list)

    # 3. start_diagnostic_quiz
    quiz_json = bridge.start_diagnostic_quiz("cli-fractions")
    quiz = json.loads(quiz_json)
    assert isinstance(quiz, list)
    if quiz:
        # 4. submit_diagnostic_quiz
        payload = json.dumps({
            "topic_id": "cli-fractions",
            "submissions": [
                {"question_id": quiz[0]["id"], "selected_option": 1, "response_time_ms": 1500}
            ]
        })
        result_json = bridge.submit_diagnostic_quiz(payload)
        result = json.loads(result_json)
        assert "topic_id" in result
        assert "initial_mastery" in result
        assert "mastery_tier" in result

