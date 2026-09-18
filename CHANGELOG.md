# Changelog

All notable changes to the Gayatri Tutor V3 project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.1.0] - 2026-09-17

### Added
- **K-12 Specialized Agent Ecosystem:**
  - Expanded registered agents to 54 total with 21 new K-12 agents (`core/agents/k12_agents.py`):
    - **STEM:** Elementary Math Tutor, Algebra Tutor, Geometry Tutor, Physics Tutor, Chemistry Tutor, Biology Tutor, Environmental Science Tutor.
    - **Humanities & Language:** History & Civics Tutor, Geography Tutor, English Grammar Coach, Reading Comprehension Coach, Creative Writing Mentor.
    - **Grade-Band Personas:** Primary School Coach (Grades 1–5), Middle School Mentor (Grades 6–8), High School & Exam Coach (Grades 9–12).
    - **Pedagogy & Study:** Socratic Questioner, Progressive Hint Giver, Doubt Buster, Formula & Theorem Companion, Quiz Master, Study Habit Coach.
- **Course-as-Markdown Ingestion Engine & CLI (`core/tutor/course_loader.py`, `scripts/ingest_course.py`):**
  - Zero-dependency built-in parser with optional PyYAML fallback.
  - Ingests YAML frontmatter, `# Heading {#topic-id}` anchors, inline `level:N` paragraphs, and ```` ```quiz ```` code blocks.
  - Command-line tool `scripts/ingest_course.py` supporting schema linting, `--validate-only`, batch directory loading, and continuous file system `--watch` mode.
- **Nightly Mastery & Progress Reporting (`scripts/nightly_mastery_report.py`):**
  - Student attempt and BKT topic mastery rollup script for teachers and parents.
  - Dual CSV and JSON report exports with per-student and per-topic aggregations (accuracy %, response times, tier distributions, and formatted ASCII summary).
- **Interactive UI Course Explorer & Diagnostic Placement Modal (`app/ui/index.html`, `app/bridge/facade.py`):**
  - Added K-12 Course Browser card grid with visual topic mastery badges (`Remedial`, `Core`, `Advanced`).
  - Interactive Diagnostic Placement Quiz modal with real-time question player, immediate scoring feedback, and one-click launch into personalized Socratic tutoring.
  - Added desktop bridge slots: `get_k12_courses()`, `get_k12_topics()`, `start_diagnostic_quiz()`, and `submit_diagnostic_quiz()`.
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
- **Comprehensive Automated Tests (`tests/test_k12_adaptive_tutor.py`):**
  - 9 dedicated behavioral tests verifying agent registration, parsing, repository CRUD, diagnostic assessment, BKT math, CLI course ingestion, nightly reporting, and bridge slots.

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
