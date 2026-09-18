# Changelog

All notable changes to the Gayatri Tutor V3 project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.1.0] - 2026-09-18

### Added (2026-09-18)
- **CLI Course Ingestion & Validation Tool (`scripts/ingest_course.py`):**
  - Command-line tool to inspect, lint, and ingest Course-as-Markdown files into SQLite.
  - Added `--validate-only` flag to verify frontmatter, heading anchors `{#topic-id}`, and ```` ```quiz ```` blocks without database writes.
  - Added `--watch` continuous monitoring mode to poll filesystem changes and automatically re-validate and re-ingest courses in real-time.
  - Batch directory ingestion supporting single `.md` files or recursive directory trees.
- **Nightly Mastery & Progress Report Generator (`scripts/nightly_mastery_report.py`):**
  - Teacher and parent reporting script rolling up student diagnostic attempts, practice attempts, and continuous BKT topic mastery.
  - Dual CSV and JSON report exports saved to `data/reports/` (or `%LOCALAPPDATA%\GayatriAI\reports`).
  - Computes accuracy %, attempt rollups, average response times, and mastery tier distributions (`Remedial`, `Core`, `Advanced`).
  - Console ASCII summary overview table for quick CLI inspection.
- **Interactive UI Course Explorer & Diagnostic Placement Modal (`app/ui/index.html`, `app/bridge/facade.py`):**
  - Added subtab toggle under Knowledge (Tab 3): `[📚 K-12 Courses]` and `[🕸 LDG Graph]`.
  - Added responsive K-12 course and topic cards showing course metadata, topic lists, question counters, and color-coded student mastery pills (`Remedial`, `Core`, `Advanced`, `Not Started`).
  - Added interactive Diagnostic Placement Quiz modal with question pagination, single-choice selection, live scoring evaluation, and a 1-click CTA button to launch personalized Socratic tutoring.
  - Added QWebChannel desktop bridge slots: `get_k12_courses()`, `get_k12_topics()`, `start_diagnostic_quiz()`, and `submit_diagnostic_quiz()`.
- **Upstream Merge & Conflict Resolution (`app/ui/index.html`):**
  - Synchronized with upstream `Gayatri-Education:main` containing Phase 3–7 performance refactors.
  - Integrated Phase 6 Central Inference Service cancellation (`bridge.cancel_generation()`) into the UI Stop button and stream lifecycle.
  - Integrated Phase 3/4 50ms rAF markdown streaming debounce (`updateStreamViewRaw` and `updateStreamView`) while preserving the atmospheric dark theme and code snippet copy cards.
- **Behavioral Test Suite Expansion (`tests/test_k12_adaptive_tutor.py`):**
  - Added tests for `validate_course` and `ingest_file` from `scripts.ingest_course`.
  - Added tests for `generate_mastery_summary` and `export_reports` from `scripts.nightly_mastery_report`.
  - Added tests for `Bridge` K-12 slots (`get_k12_courses`, `get_k12_topics`, `start_diagnostic_quiz`, `submit_diagnostic_quiz`).

### Added (2026-09-17)
- **K-12 Specialized Agent Ecosystem:**
  - Expanded registered agents to 54 total with 21 new K-12 agents (`core/agents/k12_agents.py`):
    - **STEM:** Elementary Math Tutor, Algebra Tutor, Geometry Tutor, Physics Tutor, Chemistry Tutor, Biology Tutor, Environmental Science Tutor.
    - **Humanities & Language:** History & Civics Tutor, Geography Tutor, English Grammar Coach, Reading Comprehension Coach, Creative Writing Mentor.
    - **Grade-Band Personas:** Primary School Coach (Grades 1–5), Middle School Mentor (Grades 6–8), High School & Exam Coach (Grades 9–12).
    - **Pedagogy & Study:** Socratic Questioner, Progressive Hint Giver, Doubt Buster, Formula & Theorem Companion, Quiz Master, Study Habit Coach.
- **Course-as-Markdown Ingestion Engine (`core/tutor/course_loader.py`):**
  - Zero-dependency built-in parser with optional PyYAML fallback.
  - Ingests YAML frontmatter, `# Heading {#topic-id}` anchors, inline `level:N` paragraphs, and ```` ```quiz ```` code blocks.
- **Pilot Curricula Content:**
  - Grade 5 Mathematics (`content/courses/math_g5_fractions.md`) with 3 topics and 8 embedded quiz questions.
  - Grade 8 Science (`content/courses/science_g8_cell.md`) with 3 topics and 7 embedded quiz questions.
- **Additive Persistence Layer (`core/tutor/course_repo.py`):**
  - Thread-safe SQLite tables: `k12_courses`, `k12_topics`, `k12_questions`, `k12_diagnostic_attempts`, `k12_topic_mastery`, and `k12_progress_events`.
- **Diagnostic Placement Testing (`core/tutor/student_diagnostic.py`):**
  - Balanced 5–8 placement question selection across difficulty levels 1–5.
  - Weighted baseline mastery calculation ($M_0 = \sum (correct \times diff) / \sum diff$) with pedagogical tier classification.
- **Bayesian Knowledge Tracing (BKT) Mastery Engine (`core/tutor/mastery_engine.py`):**
  - Continuous difficulty-weighted mastery updates clamped to $[0.0, 1.0]$.
  - 3-tier dynamic scaffolding context builder (`Remedial`, `Core`, `Advanced`).

### Verified
- 100% test pass rate across 246 automated tests (237 regression + 9 K-12 tests).

## [3.0.0] - 2026-09-16

### Added
- **Cryptographic Security & Signing (Phase 5):**
  - Implemented asymmetric Ed25519 signature engine (`core/security/signatures.py`).
  - Signed model manifest verification in `core/model_fetch/ollama_pull.py` preventing untrusted weights execution.
  - Automated release packaging (`scripts/package_release.py`) and cryptographic verification CLI (`scripts/verify_release.py`).
- **Productization & Governance (Phase 4):**
  - Multi-user profile management (`core/profile.py`) with profile-scoped session tracking (`core/session.py`).
  - Standardized bilingual CBSE Mathematics and NCERT Science curriculum adapters (`core/curriculum/adapters.py`).
  - Age-band safety policies and academic integrity guardrails (`core/safety.py`).
  - Parent/teacher administrative PIN protection, daily screen-time limits, and progress reporting in JSON and CSV (`core/governance.py`).
- **Engineering Maturity & Reliability (Phase 2 & 3):**
  - Automated schema migration and corruption recovery framework (`core/db.py`).
  - Learning Dependency Graph recovery mode (`core/knowledge_graph.py`, `core/tutor_engine.py`).
  - Provider lifecycle state tracking and capability-based fallback routing (`core/providers/registry.py`).
  - 3-gram Jaccard similarity training/evaluation leakage prevention (`training/validators/dataset_validator.py`).
  - Python 3.12 locked dependencies (`requirements.lock`) and GitHub Actions CI (`.github/workflows/ci.yml`).
- **Core Security & Privacy Hardening (Phase 0 & 1):**
  - Windows DPAPI secure secret storage (`core/security/secrets.py`).
  - QWebChannel bridge privilege restrictions and Content Security Policy (`app/ui/index.html`).
  - Multi-turn LLM intent evaluator for student mastery verification (`core/orchestrator.py`).
  - Formal local-only privacy contract and network audit transmission log (`docs/PRIVACY_CONTRACT.md`, `core/providers/base.py`).

### Changed
- Refactored brittle source-text assertions into behavioral test fixtures.
- Decoupled `LLMProvider` base class from singleton local provider assumptions.
- Upgraded SQLite connections to enforce WAL mode, synchronous=NORMAL, and foreign key constraints across concurrent worker threads.

### Verified
- 100% test pass rate across 228 automated behavioral and regression tests.
- Section 31 "Production-Ready" Acceptance Gate fully satisfied.
