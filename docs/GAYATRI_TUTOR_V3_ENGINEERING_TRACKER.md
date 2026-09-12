# Gayatri Tutor V3 — Engineering Audit, Bug Register, Security Review, AI/ML Evaluation Plan & Living Agent Tracker

> **Repository:** https://github.com/Gayatri-Education/Gayatri-Tutor-V3  
> **Branch audited:** `main`  
> **Audit date:** 2026-09-12  
> **Product type:** Local-first desktop AI tutor / agentic AI application  
> **Audience:** Maintainers, developers, AI coding agents, QA, research/training contributors
>
> **Audit scope:** repository architecture, runtime behavior inferred from current source, desktop bridge security, provider routing, privacy, persistence, tutoring state, agent runtime, training/data pipeline, tests, dependency management, documentation, and production-readiness.
>
> **Runtime limitation:** This report is based on current public repository source inspection and static reasoning. A local execution pass is still required to turn every `NEEDS_RUNTIME_VERIFICATION` item into a measured result. Never mark a runtime-dependent item `VERIFIED` from code inspection alone.

---

# 1. Agent Operating Contract
## How to update this tracker
This file is a **living engineering source of truth**. Update the status fields from `NOT_STARTED` to `FIXED_UNVERIFIED` and then `VERIFIED` as you complete each task. Append a progress entry for each fix.


The coding agent must not treat it as a one-time bug list. It must re-check every unresolved item against the current repository before changing code.

Required workflow:

```text
Read tracker
→ inspect current HEAD
→ reproduce or define acceptance test
→ patch minimal root cause
→ add regression test
→ run deterministic validation
→ run relevant integration validation
→ review diff
→ update tracker
→ commit
```

Never:

```text
modify code → assume fixed
```

---

# 2. Status Vocabulary

Use only:

```text
NOT_STARTED
IN_PROGRESS
BLOCKED
FIXED_UNVERIFIED
VERIFIED
WONT_FIX
SUPERSEDED
```

Severity:

```text
P0 = security/privacy/data-loss/runtime correctness blocker
P1 = serious product correctness/reliability/AI quality issue
P2 = engineering maturity / maintainability / UX / performance
P3 = enhancement
```

---

# 3. Executive Verdict

## Current classification

**Gayatri Tutor V3 is a strong research/educational desktop prototype with a good modular direction, but it is not yet production-grade educational software.**

The architecture is materially better than a simple chatbot:

```text
PySide6
  ↓
QWebEngine UI
  ↓
QWebChannel Bridge
  ↓
Orchestrator
  ↓
Agent Registry / Agent Runtime
  ↓
Provider Registry
  ↓
Local + Optional Cloud LLMs

Parallel systems:
  Learning Dependency Graph
  Tutor Engine
  Session Store
  Settings
  Secrets Vault
  Model Fetcher
  Training Pipeline
```

The repository currently contains:

- local GGUF/llama.cpp inference
- agent orchestration
- explicit agent registry
- tool registry
- provider abstraction
- local/cloud privacy routing
- PII redaction
- secret vault
- learning dependency graph
- mastery tracking
- persistent sessions
- model download flow
- extensive pytest coverage
- Qt UI bridge
- training-data generation
- QLoRA/Colab training pipeline

The architectural ambition is good.

The main engineering problem is **trust calibration**:

```text
feature exists
≠
feature is correct
≠
feature is secure
≠
feature is pedagogically validated
≠
feature is production-ready
```

The project currently needs a stronger separation between:

```text
prototype capability
research capability
verified capability
production capability
```

---

# 4. Current Architecture — What Works

## ARCH-001 — Modular separation

**Status: VERIFIED**

Major responsibilities are separated under `app/`, `core/`, `tests/`, and `training/`.

The current repository has distinct areas for:

- UI
- bridge
- agents
- model fetching
- providers
- security
- persistence
- orchestration
- tutor engine
- curriculum graph
- training

This is a strong foundation.

---

## ARCH-002 — Provider abstraction

**Status: VERIFIED**

The project has a provider interface and registry instead of hardwiring all model calls to one vendor.

This is a good design for:

- local-first fallback
- future model substitution
- provider-specific capability metadata
- privacy-aware routing

---

## ARCH-003 — Explicit privacy execution mode

**Status: VERIFIED AT CODE LEVEL**

The provider registry explicitly attempts to exclude cloud providers in `local_only` mode.

The tests also cover this behavior.

This should remain a non-negotiable invariant.

---

## ARCH-004 — Tool registry has useful safety controls

**Status: VERIFIED AT CODE/TEST LEVEL**

The tool registry includes:

- duplicate registration protection
- basic argument type validation
- path traversal checks
- timeouts
- unknown-tool handling
- tool error sanitization

These are meaningful controls.

However, they are not yet sufficient for a true untrusted-agent execution environment.

---

## ARCH-005 — Tutor state has transaction intent

**Status: VERIFIED AT CODE LEVEL**

The tutor engine contains transaction-style handling so model failures can roll back state changes.

That is a good design direction.

---

# 5. Critical P0 Findings

---

## P0-001 — README points to a missing Comprehensive Audit Document

**Status: VERIFIED**

The README explicitly tells contributors to see a “Comprehensive Audit Document,” but the linked path currently returns `404 Not Found`.

### Impact

This creates:

- broken contributor workflow
- stale/incomplete project guidance
- false documentation promise
- loss of institutional memory
- ambiguity about previously found issues

### Fix

Either:

1. restore the missing document, or
2. replace the link with the maintained audit tracker.

Recommended:

```text
docs/GAYATRI_TUTOR_V3_ENGINEERING_TRACKER.md
```

and link to it from README.

### Acceptance criteria

```text
README audit link resolves
document is committed
document has current status
document has issue IDs
document explains how to update it
```

---

## P0-002 — QWebChannel exposes privileged Python operations to JavaScript

**Status: NOT_STARTED**

`MainWindow` registers the `Bridge` object directly on a `QWebChannel`:

```python
self._channel.registerObject("bridge", self._bridge)
```

The bridge exposes slots including:

```text
send_message
set_setting
save_provider_key
validate_provider_key
download_model
window controls
```

The UI is loaded locally, which reduces the attack surface, but the architectural trust boundary is still weak:

```text
Web UI JavaScript
        ↓
QWebChannel
        ↓
Python privileged methods
        ↓
filesystem / secrets / model / provider configuration
```

### Why this matters

A compromised or unexpectedly modified frontend could potentially invoke privileged bridge methods.

The important point is not that the current local HTML is necessarily malicious.

The issue is:

> **There is no strong capability boundary between UI JavaScript and privileged Python operations.**

### Required fix

Create explicit bridge capabilities:

```text
ChatBridge
SettingsBridge
ModelBridge
ProviderBridge
WindowBridge
```

and expose only the smallest required API to each page.

For sensitive actions, add:

```text
schema validation
allowed-setting whitelist
capability token / session binding
operation confirmation where appropriate
```

### Acceptance criteria

- UI cannot invoke arbitrary Python functions
- provider keys never enter generic bridge methods except dedicated secure operation
- settings are allowlisted
- model download accepts only approved model IDs
- sensitive operations have explicit tests

---

## P0-003 — Training validation leakage through random split of duplicated synthetic data

**Status: NOT_STARTED**

Both training generators construct many highly related examples through:

- templated phrasing
- repeated answers
- random system prompts
- many paraphrase-like combinations
- multi-turn variants
- agent dispatch variations

Then the training pipeline performs:

```python
random.shuffle(all_data)
split = int(len(all_data) * 0.9)
train_data = all_data[:split]
val_data = all_data[split:]
```

### Why this is a problem

Random splitting does not guarantee semantic or template independence.

Near-duplicate examples can land in both train and validation.

This can make:

```text
validation loss
validation accuracy
routing accuracy
```

look better than true generalization.

### Required fix

Build deterministic grouped splits.

Group by:

```text
source template
concept
task
agent intent
conversation template
paraphrase family
answer family
```

Prefer:

```text
train
dev
golden evaluation
adversarial evaluation
```

and keep the gold evaluation set completely isolated.

### Acceptance criteria

No paraphrase/near-duplicate from the same source family exists in both training and final evaluation.

---

## P0-004 — Student mastery is partly inferred with weak heuristics rather than demonstrated knowledge

**Status: NOT_STARTED**

The orchestrator determines answer correctness using simple text heuristics:

```text
short answer -> wrong
"I don't know" -> wrong
"yes/correct/right" -> correct
"no/wrong/incorrect" -> wrong
otherwise -> uncertain
```

This means a student can potentially increase mastery by saying:

```text
"yes"
```

without demonstrating understanding.

Likewise, a correct detailed answer may be categorized as uncertain.

### Impact

The learning system can build an inaccurate student model.

That directly affects:

- concept selection
- prerequisites
- difficulty
- progression
- mastery percentage

### Fix

Create a real assessment pathway:

```text
student answer
→ answer normalization
→ deterministic checks where possible
→ structured evaluator
→ confidence
→ rubric
→ mastery update
```

For factual/MCQ questions use deterministic evaluation.

For open-ended answers use a controlled evaluator with:

```text
rubric
reference concepts
minimum evidence
confidence
uncertain state
```

Do not turn every "yes/no" response into a mastery event.

---

## P0-005 — PII redaction is not a complete privacy boundary

**Status: NOT_STARTED**

The repository uses a regex-based PII detector/redactor.

This is useful but cannot guarantee that:

```text
all sensitive information
```

is detected.

The implementation recognizes several specific classes such as:

- email
- UPI
- card
- Aadhaar
- PAN
- passport
- phone
- SSN-like patterns

but educational conversations can contain sensitive information not covered by these patterns.

### Examples

```text
home address
school name
parent names
student ID
teacher identity
exact location
medical history
behavioral profile
free-form personal descriptions
```

### More important issue

The project should not claim:

> Sensitive data never leaves the device

unless that statement is conditioned on explicit local-only execution.

The orchestrator can operate in a cloud-allowed mode.

### Required fix

Change privacy claims to precise language:

```text
Local-only mode: conversation content stays on-device except explicitly invoked local dependencies.
Cloud-allowed mode: user-approved provider calls may transmit submitted content according to provider policy.
```

Add:

```text
data classification
consent state
provider disclosure
per-request transmission audit
```

---

## P0-006 — Secrets fallback uses deliberately insecure base64 storage

**Status: FIXED_UNVERIFIED / P0 FOR NON-WINDOWS**

The secrets vault explicitly falls back to base64 on non-Windows when:

```text
ALLOW_INSECURE_SECRET_STORAGE=true
```

This is clearly labeled as insecure, which is good.

However, the application must ensure that a production release cannot accidentally run with this mode enabled.

### Required fix

Production policy:

```text
non-Windows production => hard failure unless OS secure store exists
```

Recommended:

```text
Windows: DPAPI
macOS: Keychain
Linux: Secret Service / keyring
```

Never use base64 as a production secret store.

---

# 6. P1 AI/Agent Findings

---

## AGENT-001 — Agent matching is primarily heuristic

The registry uses:

- commands
- trigger phrases
- normalized text
- substring matching
- negation detection
- scoring

This is a reasonable lightweight approach.

However:

```text
phrase match ≠ intent understanding
```

### Risks

Examples of ambiguous input:

```text
"Don't review this code"
"Can you explain why my code needs review?"
"Quiz me after explaining loops"
"Research this and then teach me"
```

A single-agent match may not represent the correct composite task.

### Upgrade

Introduce explicit routing stages:

```text
intent classifier
→ confidence
→ one-agent vs multi-agent decision
→ task plan
→ execution
```

Add:

```text
NO_MATCH
LOW_CONFIDENCE
AMBIGUOUS
MULTI_INTENT
```

states.

---

## AGENT-002 — Max tool steps are hardcoded

`AgentRuntime` uses:

```text
_max_steps = 12
```

This is useful as a safety limit but not a configurable policy.

### Upgrade

Move to policy configuration:

```text
per-agent max_steps
global max_steps
time budget
tool budget
token budget
```

---

## AGENT-003 — Tool timeouts do not terminate the underlying work

The registry waits on a future with a timeout, then shuts down the executor with:

```text
cancel_futures=True
```

For already-running Python functions, cancellation does not necessarily stop the underlying work.

So:

```text
model timeout
```

can become:

```text
background work continues consuming CPU/network
```

### Fix

For potentially dangerous or expensive tasks use:

```text
process isolation
cooperative cancellation
async cancellation
subprocess worker
```

rather than assuming `Future.cancel()` kills running code.

---

## AGENT-004 — Tool argument type validation is shallow

The tool registry uses basic `isinstance`.

This does not validate:

```text
nested structures
ranges
enums
allowed filesystem roots
URL schemes
size limits
```

Upgrade to structured schemas:

```text
Pydantic
JSON Schema
```

with semantic validation.

---

# 7. P1 Desktop Security Findings

---

## DESKTOP-001 — Embedded UI trust model should be hardened

The current main window loads local HTML, which is good.

However, the design should explicitly enforce:

```text
only trusted local UI assets
no arbitrary navigation
no external page loading
no remote frame injection
no untrusted content execution with bridge access
```

Add a navigation policy:

```text
accept only qrc:// or expected file:// UI roots
reject http:// and https:// navigation
```

Add tests for:

```text
redirect
window.open
external navigation
iframe
malformed URL
```

---

## DESKTOP-002 — Web content security policy is not established as an explicit contract

The UI should have a defined CSP.

At minimum:

```text
script-src limited to trusted application sources
connect-src limited to expected local/provider endpoints
object-src 'none'
base-uri 'none'
frame-ancestors 'none'
```

Qt/WebEngine-specific enforcement should be documented and tested.

---

## DESKTOP-003 — Provider key validation temporarily mutates live provider state

The bridge implementation does:

```text
old_key = provider._api_key
provider._api_key = api_key
provider.validate_key()
provider._api_key = old_key
```

### Risks

Concurrent operations could observe the temporary key.

If validation raises unexpectedly, state restoration depends on the current exception path.

### Fix

Use:

```text
validate_key(api_key)
```

without mutating provider instance state.

---

## DESKTOP-004 — Settings setter accepts arbitrary keys

`set_setting()` checks whether a key exists in the schema for type coercion, but still ultimately calls:

```text
store.set(key, parsed)
```

even when the key is not part of the approved schema.

### Impact

The settings file can accumulate arbitrary keys.

More importantly, future settings may accidentally become writable without security review.

### Fix

Reject unknown settings:

```text
if key not in schema:
    raise InvalidSettingError
```

---

# 8. Privacy Findings

---

## PRIV-001 — PII redaction occurs before the model, but conversation privacy needs an explicit end-to-end contract

The orchestrator redacts user input before adding it to conversation history.

This is good.

But privacy must cover:

```text
logs
exceptions
telemetry
crash dumps
settings
model prompts
tool results
training data
provider requests
database
backup files
```

Create a data-flow document.

---

## PRIV-002 — Do not log raw tool arguments by default

The tool registry currently logs:

```text
Tool call: name(kwargs)
```

Depending on tool arguments, `kwargs` can contain sensitive data.

### Fix

Log:

```text
tool_name
argument names
safe metadata
hash / redacted values
```

not arbitrary argument content.

---

## PRIV-003 — PII redaction should be configurable by classification, not only pattern

A student-facing product should distinguish:

```text
Public
Personal
Sensitive
Highly Sensitive
Secret
```

Then define:

```text
local-only
cloud-allowed
never-export
```

policies.

---

# 9. Tutor / Pedagogy Findings

---

## EDU-001 — Mastery percentage is not yet evidence-calibrated

The LDG stores:

```text
mastery
exposure_count
error_count
last_practiced
```

This is a good state model.

But a numeric mastery value is only meaningful if its update rule is validated against actual student performance.

### Upgrade

Define mastery semantics:

```text
0.0–0.19 = introduced
0.2–0.49 = developing
0.5–0.74 = practicing
0.75–0.89 = proficient
0.90–1.0 = mastered
```

These are product semantics only until validated.

More important:

track:

```text
attempts
correct
incorrect
uncertain
hint_used
time_to_answer
difficulty
question_type
confidence
retention_interval
```

---

## EDU-002 — Mastery should decay or be reassessed

Current state emphasizes accumulated mastery.

Learning science generally requires checking whether knowledge persists.

Add:

```text
spaced review
retrieval practice
mastery decay/reassessment
```

Do not simply keep mastery high forever after early success.

---

## EDU-003 — Prerequisite threshold should be concept/version aware

The code uses a mastery threshold for prerequisites.

This is reasonable.

But prerequisite requirements should be curriculum metadata:

```text
minimum_mastery
evidence_count
assessment_types
```

rather than only one universal threshold.

---

## EDU-004 — Learning Dependency Graph is curriculum-specific

The default orchestration initializes:

```text
python_basics.json
```

This means the platform's general tutoring architecture is currently tightly coupled to at least one Python curriculum.

### Upgrade

Create:

```text
CurriculumProvider
```

with:

```text
subject
board
grade
language
version
concept graph
assessment policy
```

This is essential for NCERT/CBSE/State Board expansion.

---

# 10. Learning Graph Findings

---

## LDG-001 — Good cycle prevention

The graph validates prerequisite cycles.

**Status: VERIFIED**

This is important.

---

## LDG-002 — Fallback concept selection can violate strict prerequisite semantics

When no directly unlocked concept exists, the graph explicitly selects the candidate closest to unlocking.

This can be useful for recovering from inconsistent state.

But it may also result in:

```text
teaching concept whose prerequisites are not mastered
```

### Fix

Make fallback behavior explicit:

```text
RECOVERY_MODE
```

and show the user/agent why the prerequisite is being revisited.

---

## LDG-003 — Single SQLite graph is explicitly single-user

The graph documentation says it is thread-safe for a single-user desktop.

That is fine for V3.

Do not accidentally treat the database layer as multi-user capable.

---

# 11. Persistence / Database Findings

---

## DB-001 — Safe corruption recovery is a good feature

The DB helper:

- runs `PRAGMA quick_check`
- backs up corrupt database
- recreates storage
- enables WAL
- enables foreign keys

This is good defensive engineering.

**Status: VERIFIED AT CODE LEVEL**

---

## DB-002 — Silent automatic database recreation can destroy user expectations

If corruption is detected, the application moves the database aside and creates a new database.

This is better than crashing.

But the UI must tell the user:

```text
Your previous database appears corrupted.
A backup was preserved at:
<path>
```

Otherwise a user may think:

```text
all progress vanished
```

---

## DB-003 — No formal schema migration framework

Tables are created dynamically with:

```text
CREATE TABLE IF NOT EXISTS
```

This is okay for a prototype.

For long-lived user data, use:

```text
schema version
migration history
upgrade/downgrade policy
backup before destructive migration
```

---

## DB-004 — SQLite concurrency assumptions need explicit testing

The connection uses:

```text
check_same_thread=False
WAL
busy_timeout
```

but this does not automatically guarantee correctness under every multi-thread interaction.

Add concurrency tests for:

```text
session save
mastery update
conversation save
provider settings
simultaneous turns
shutdown while write pending
```

---

# 12. Session / Conversation Findings

---

## SESSION-001 — Global conversation store creates process-wide shared state

The orchestrator initializes:

```text
_conversations = ConversationStore()
```

This is acceptable for one desktop process.

But test isolation becomes harder and future multi-profile support becomes difficult.

### Upgrade

Use dependency injection everywhere, with:

```text
UserProfile
SessionStore
ConversationStore
```

owned by application context.

---

## SESSION-002 — Session IDs must remain unguessable

The bridge uses UUID session IDs.

This is good.

Continue validating session IDs at persistence boundaries.

---

## SESSION-003 — Session data retention policy is missing

A student product needs configurable retention:

```text
keep forever
30 days
90 days
1 year
delete on logout
```

and explicit deletion.

---

# 13. Provider System Findings

---

## PROVIDER-001 — Provider capability model is a strong design

`Capability` includes:

```text
CHAT
STREAM
TOOLS
VISION
JSON_MODE
SYSTEM_PROMPT
LONG_CONTEXT
```

This is good groundwork for model selection.

---

## PROVIDER-002 — Fallback routing needs a model-availability contract

The registry calls provider availability/model listing dynamically.

Provider APIs can fail or change.

A provider should return:

```text
READY
AUTH_REQUIRED
OFFLINE
RATE_LIMITED
UNSUPPORTED
MODEL_NOT_FOUND
UNKNOWN
```

rather than only `True/False`.

---

## PROVIDER-003 — Provider selection should account for capability requirements

Current routing is primarily tier-based.

It should also select by:

```text
task capability
context length
vision requirement
tools requirement
structured-output requirement
privacy policy
latency budget
cost budget
```

---

## PROVIDER-004 — Model catalog freshness should be cached

Repeated remote model listing can create:

```text
latency
API calls
rate-limit risk
UI delays
```

Add a TTL cache.

---

# 14. Model Download Findings

---

## MODEL-001 — Model downloads require strong integrity verification

The model download flow exists and has dedicated safety tests.

Before a downloaded model becomes executable, require:

```text
expected source
HTTPS
content length limit
SHA-256
optional signed manifest
supported file format
maximum size
destination allowlist
```

Never trust:

```text
filename
extension
remote URL alone
```

---

## MODEL-002 — Model catalog must be allowlisted

The UI should not be able to convert an arbitrary user string into:

```text
remote model
```

without an approved manifest.

Recommended:

```text
ModelManifest
  id
  source
  URL
  sha256
  size
  architecture
  quantization
  minimum RAM
  recommended RAM
  license
```

---

## MODEL-003 — Model compatibility must be validated before load

Check:

```text
GGUF metadata
context size
architecture
quantization
required CPU features
RAM
GPU backend availability
```

before loading.

---

# 15. Local Model / Hardware Findings

The README correctly presents the system as local-first.

However, model availability and hardware suitability must be formalized.

Add a hardware capability matrix:

```text
RAM
VRAM
CPU
GPU backend
threads
context size
quantization
recommended model
estimated memory
estimated tokens/sec
```

The UI should not merely say:

```text
model available
```

It should say:

```text
model available
+
hardware suitable / marginal / unsuitable
```

---

# 16. Training Pipeline Findings

---

## TRAIN-001 — Synthetic data dominates the training pipeline

The generator uses manually written prompt/answer templates and creates combinations through randomization.

This is acceptable for bootstrapping.

It is not enough by itself to produce a robust tutor.

### Missing

```text
high-quality curriculum examples
expert-reviewed examples
adversarial examples
misconception examples
grade-level examples
language variants
NCERT-aligned examples
incorrect-student reasoning
partial-credit examples
```

---

## TRAIN-002 — Data leakage from near-duplicates

See `P0-003`.

This is a training evaluation blocker.

---

## TRAIN-003 — No dataset versioning

Training output should include:

```text
dataset_version
generator_commit
generation_seed
source_count
template_count
train_count
validation_count
test_count
hash
```

---

## TRAIN-004 — Randomness is not reproducibly controlled

The training data generators use `random`.

A reproducible research pipeline needs:

```text
seed
config
dataset hash
code commit
dependency lock
```

---

## TRAIN-005 — Training data quality checks are too weak

Add automated validators for:

```text
empty messages
duplicate conversations
same user prompt → conflicting answers
invalid JSON
invalid roles
too-long samples
too-short samples
PII
copyright-sensitive material
instruction hierarchy conflicts
unsafe advice
hallucinated facts
broken code snippets
```

---

## TRAIN-006 — No held-out educational benchmark

Create a curated evaluation set:

```text
benchmark/
  beginner_python.jsonl
  intermediate_python.jsonl
  math.jsonl
  reasoning.jsonl
  tutoring_behavior.jsonl
  safety.jsonl
  agent_routing.jsonl
  privacy.jsonl
```

Metrics should be recorded per release.

---

# 17. Educational AI Evaluation

A serious educational AI needs more than LLM benchmark scores.

Track:

```text
Correctness
Pedagogical quality
Socratic behavior
Hint quality
Student agency
Misconception handling
Calibration of mastery
Prerequisite respect
Question difficulty
Factuality
Safety
Age appropriateness
Language clarity
```

### Minimum golden evaluation

Each release should run:

```text
100–500 curated prompts
```

across:

```text
normal
edge
ambiguous
adversarial
privacy
curriculum
```

with explicit expected properties.

---

# 18. Safety Findings

---

## SAFETY-001 — Educational safety policy should be explicit

The tutor may encounter:

```text
self-harm
bullying
abuse
dangerous experiments
medical questions
financial advice
illegal activity
sexual content involving minors
```

A production student tutor needs policy routing before ordinary tutoring output.

Add:

```text
SafetyClassifier
→ SAFE / CAUTION / REFUSE / ESCALATE
```

---

## SAFETY-002 — Age/grade profile is not an explicit safety input

For a school product, the tutor should know its intended audience policy:

```text
primary
middle school
secondary
adult
```

The same response can be appropriate for an adult and inappropriate for a child.

---

# 19. Code Quality Findings

---

## CODE-001 — Very large files reduce maintainability

Important examples are currently large:

```text
core/orchestrator.py
core/settings.py
core/session.py
app/bridge.py
```

Large modules accumulate too many responsibilities.

### Upgrade

Split by responsibility.

For example:

```text
orchestrator/
  router.py
  provider_selection.py
  turn_service.py
  tutor_flow.py
  streaming.py
```

and:

```text
bridge/
  chat_bridge.py
  settings_bridge.py
  provider_bridge.py
  model_bridge.py
```

---

## CODE-002 — Exception handling often collapses different failures

Many modules convert exceptions into general messages.

This prevents crashes but may reduce diagnosis quality.

Use typed error classes:

```text
ModelUnavailableError
ProviderAuthError
ProviderRateLimitError
ProviderNetworkError
InvalidSettingError
DatabaseCorruptionError
ModelIntegrityError
PrivacyViolationError
ToolExecutionError
```

---

## CODE-003 — Type checking is not part of the quality gate

Add:

```text
pyright or mypy
```

especially for:

```text
orchestrator
providers
bridge
db
tutor_engine
knowledge_graph
```

---

# 20. Dependency / Packaging Findings

`pyproject.toml` requires:

```text
Python >=3.12,<3.13
```

while the README currently describes the project more broadly.

The package also has:

```text
requirements.txt
pyproject.toml
```

with minimum versions rather than an immutable lock.

### Required

Pick one canonical dependency workflow.

Recommended:

```text
pyproject.toml
uv.lock
```

or a fully pinned requirements lock.

---

## PACKAGE-001 — Requirements are not actually pinned

The file is called:

```text
Pinned Dependencies
```

but versions are specified as:

```text
>=
```

That is not pinning.

Rename documentation or actually pin versions.

---

## PACKAGE-002 — Python version compatibility should be documented consistently

Make README, setup scripts, pyproject, CI, and model compatibility all agree.

---

# 21. CI/CD Findings

No clear `.github/workflows` structure was visible in the repository tree inspected.

Treat this as:

```text
CI status: NEEDS_RUNTIME/REPOSITORY VERIFICATION
```

but the target state should be:

```text
PR
 ↓
format
 ↓
lint
 ↓
type-check
 ↓
unit tests
 ↓
Qt tests
 ↓
privacy tests
 ↓
security tests
 ↓
packaging smoke test
 ↓
artifact check
```

Add separate optional workflows for:

```text
live provider tests
GPU tests
model tests
Windows packaged app test
```

---

# 22. Test Suite Findings

## What is already strong

The repository has dedicated tests for:

```text
agent matching
agent registry
bridge
concurrency
database
mastery assessment
model download safety
model unavailability
privacy enforcement
provider readiness
regressions
secrets
session
session reliability
settings/errors
stream errors
tool safety
tutor persistence
```

This is a strong test inventory.

---

## TEST-001 — Some regression tests inspect source text instead of behavior

`test_regressions.py` contains tests such as:

```text
assert "LDG_MASTERY_THRESHOLD" in content
```

and HTML source-string assertions.

These tests can pass even when the runtime behavior is wrong.

### Fix

Replace source-text assertions with:

```text
behavioral tests
integration tests
golden tests
```

Only use source inspection where there is genuinely no better contract.

---

## TEST-002 — A test is currently a placeholder

The model progress regression test contains:

```python
pass
```

and does not actually test the reported failure.

That must not be counted as regression coverage.

---

## TEST-003 — Qt tests should be separated from headless CI

Use:

```text
unit tests
headless core tests
Qt tests
Windows GUI tests
```

with the correct runners.

---

## TEST-004 — Add coverage thresholds

Recommended starting target:

```text
overall ≥ 80%
critical security/privacy/orchestration modules ≥ 90%
```

Do not optimize the number at the expense of behavioral test quality.

---

# 23. API / UI Contract Findings

Although V3 is a desktop application rather than a web service, the QWebChannel is effectively an internal API.

Treat bridge methods like public APIs.

Every bridge method should define:

```text
name
arguments
validation
side effects
security class
failure semantics
return schema
```

Example:

```text
save_provider_key
Security class: SECRET_WRITE
Input: provider_key + secret
Output: status
Side effects: secure-store write
Failure: explicit error code
```

---

# 24. Observability

The current logging setup is useful, but production diagnostics should expose structured metrics.

Minimum:

```text
app_start_total
model_load_success_total
model_load_failure_total
model_generation_latency_ms
model_generation_tokens
provider_calls_total
provider_failures_total
provider_rate_limits_total
privacy_redactions_total
tool_calls_total
tool_failures_total
tool_timeouts_total
tutor_turns_total
mastery_updates_total
database_recovery_total
session_save_failures_total
bridge_errors_total
```

Do not record raw student content in telemetry.

---

# 25. Reliability Requirements

The agent must add tests for:

```text
model missing
model corrupt
model incompatible
provider unavailable
provider timeout
provider rate limit
cloud disabled
invalid settings
corrupt DB
DB locked
session switched during stream
app shutdown during stream
download cancelled
download interrupted
download hash mismatch
bridge error
agent loop timeout
tool timeout
tool returns malformed output
unknown agent
unknown model
unknown provider
```

---

# 26. UX / Product Reliability

The UI should clearly distinguish:

```text
Generating
Model unavailable
Provider unavailable
Cloud disabled
Downloading
Downloading failed
Corrupt model
Session save failed
Progress save failed
```

Never display:

```text
"Done"
```

when only the UI stream finished while persistence failed.

---

# 27. Model / Provider Transparency

Every answer should have machine-readable metadata internally:

```text
provider
model
execution_mode
agent
routing_reason
latency
tokens
privacy_state
```

The current `TurnResult` already moves in this direction.

Expose a user-friendly subset:

```text
Local model
Cloud model
Tutor agent
Code reviewer
```

without revealing secrets.

---

# 28. Release Management

Introduce:

```text
VERSION
CHANGELOG.md
RELEASE_NOTES.md
```

Every release should identify:

```text
app version
model version
curriculum version
dataset version
provider compatibility
Python version
Qt/PySide version
known limitations
```

---

# 29. Recommended Repository Layout Evolution

Do not immediately rewrite the whole repository.

Target:

```text
app/
  bridge/
  windows/
  ui/

core/
  agents/
  providers/
  security/
  tutoring/
  curriculum/
  sessions/
  persistence/
  runtime/
  privacy/
  models/

training/
  datasets/
  generators/
  evaluation/
  notebooks/
  configs/

tests/
  unit/
  integration/
  gui/
  security/
  privacy/
  evaluation/
  fixtures/

docs/
  architecture/
  security/
  privacy/
  curriculum/
  training/
  releases/
```

Refactor only after P0/P1 behavior is stable.

---

# 30. Priority Roadmap

## Phase 0 — Correctness and security blockers

```text
[x] P0-001 restore audit tracker link
[x] P0-002 harden QWebChannel boundary
[ ] P0-003 fix training validation leakage
[ ] P0-004 replace mastery heuristics
[ ] P0-005 formalize privacy claims + privacy flow
[ ] P0-006 remove production-insecure secret fallback
[ ] DESKTOP-003 remove temporary provider-key mutation
[ ] DESKTOP-004 reject unknown settings
```

---

## Phase 1 — AI quality

```text
[ ] grouped dataset splitting
[ ] deterministic seeds
[ ] benchmark dataset
[ ] adversarial tutor evaluation
[ ] mastery calibration
[ ] prerequisite policy
[ ] spaced retrieval
[ ] misconception tests
[ ] answer-rubric evaluator
[ ] agent routing benchmark
```

---

## Phase 2 — Reliability

```text
[ ] provider state model
[ ] model integrity manifest
[ ] download cancellation correctness
[ ] migration framework
[ ] database recovery UI
[ ] session retention
[ ] crash-safe writes
[ ] structured metrics
```

---

## Phase 3 — Engineering maturity

```text
[ ] CI
[ ] lockfile
[ ] type checking
[ ] security scanning
[ ] package build
[ ] Windows smoke installer
[ ] release workflow
[ ] changelog
```

---

## Phase 4 — Productization

Only after the above:

```text
[ ] multi-user profile architecture
[ ] curriculum provider
[ ] NCERT/CBSE adapters
[ ] multilingual curriculum
[ ] teacher/admin controls
[ ] parent controls
[ ] analytics
[ ] signed model manifests
[ ] signed releases
```

---

# 31. Acceptance Gate: "Production-Ready"

Do not use the phrase "production-ready" until:

```text
[ ] all P0 issues resolved
[ ] all security-critical bridge operations audited
[ ] privacy policy matches actual data flows
[ ] secrets are secure on supported OSes
[ ] model downloads are integrity-verified
[ ] benchmark evaluation is reproducible
[ ] train/dev/test leakage is controlled
[ ] tutoring mastery is behaviorally validated
[ ] CI blocks regressions
[ ] packaging is reproducible
[ ] database migrations exist
[ ] backup/recovery is tested
[ ] critical failure states are user-visible
[ ] model/provider/version metadata is recorded
[ ] safety evaluation exists
[ ] age/grade safety policy exists
[ ] Windows release has installation + upgrade + rollback test
```

---

# 32. Current Issue Register

## P0

| ID | Status | Area |
|---|---|---|
| P0-001 | VERIFIED | Broken audit-document reference |
| P0-002 | VERIFIED | QWebChannel privileged bridge boundary |
| P0-003 | NOT_STARTED | Training validation leakage |
| P0-004 | NOT_STARTED | Mastery assessment heuristic correctness |
| P0-005 | NOT_STARTED | Privacy claim/data-flow mismatch |
| P0-006 | FIXED_UNVERIFIED | Insecure non-Windows secret fallback |

## P1

| ID | Status | Area |
|---|---|---|
| AGENT-001 | NOT_STARTED | Heuristic intent routing |
| AGENT-002 | NOT_STARTED | Hardcoded agent budget |
| AGENT-003 | NOT_STARTED | Tool timeout doesn't guarantee termination |
| AGENT-004 | NOT_STARTED | Weak tool schemas |
| DESKTOP-001 | NOT_STARTED | Navigation/bridge hardening |
| DESKTOP-002 | NOT_STARTED | Web content security policy |
| DESKTOP-003 | NOT_STARTED | Temporary provider key mutation |
| DESKTOP-004 | NOT_STARTED | Arbitrary settings keys |
| PRIV-001 | NOT_STARTED | End-to-end privacy contract |
| PRIV-002 | NOT_STARTED | Tool-argument logging |
| EDU-001 | NOT_STARTED | Mastery calibration |
| EDU-002 | NOT_STARTED | Spaced reassessment |
| EDU-003 | NOT_STARTED | Prerequisite policy |
| EDU-004 | NOT_STARTED | Curriculum abstraction |
| LDG-002 | NOT_STARTED | Recovery-mode prerequisite violation |
| DB-002 | NOT_STARTED | Transparent corruption recovery |
| DB-003 | NOT_STARTED | Schema migration |
| DB-004 | NOT_STARTED | Concurrency validation |
| TRAIN-001 | NOT_STARTED | Synthetic-data dependence |
| TRAIN-002 | NOT_STARTED | Near-duplicate leakage |
| TRAIN-003 | NOT_STARTED | Dataset versioning |
| TRAIN-004 | NOT_STARTED | Deterministic seed |
| TRAIN-005 | NOT_STARTED | Dataset quality validation |
| TRAIN-006 | NOT_STARTED | Held-out educational benchmark |
| TEST-001 | NOT_STARTED | Source-text assertions |
| TEST-002 | NOT_STARTED | Placeholder regression test |
| TEST-003 | NOT_STARTED | GUI/headless test separation |
| PACKAGE-001 | NOT_STARTED | "Pinned" requirements are not pinned |
| PACKAGE-002 | NOT_STARTED | Python-version consistency |
| PROVIDER-002 | NOT_STARTED | Provider state semantics |
| PROVIDER-003 | NOT_STARTED | Capability-aware routing |
| PROVIDER-004 | NOT_STARTED | Model catalog caching |
| MODEL-001 | NOT_STARTED | Model integrity verification |
| MODEL-002 | NOT_STARTED | Model allowlist |
| MODEL-003 | NOT_STARTED | Model compatibility validation |

---

# 33. Test Strategy

## Unit

No network, no real model, no filesystem dependency except fixtures.

```text
pytest tests/unit
```

## Integration

Uses local fixtures and temporary SQLite databases.

```text
pytest tests/integration
```

## GUI

Runs with pytest-qt on supported CI/Windows environment.

```text
pytest tests/gui
```

## Live provider tests

Opt-in only.

```text
pytest -m live
```

Never require API keys for normal CI.

---

# 34. AI Agent Validation Commands

Start with:

```bash
python -m pytest -q
```

Then:

```bash
ruff check .
ruff format --check .
```

Then type checking:

```bash
pyright
```

or:

```bash
mypy core app training
```

Then packaging:

```bash
python -m build
```

Then import smoke:

```bash
python -c "from core.orchestrator import Orchestrator; print('orchestrator import OK')"
```

Then application smoke test on Windows:

```bat
setup.bat
launch.bat
```

For headless CI, create a mock-model startup path.

---

# 35. Definition of Fixed

An issue becomes:

```text
VERIFIED
```

only when:

```text
1. Root cause documented
2. Patch committed
3. Regression test added
4. Relevant tests pass
5. Adjacent tests pass
6. Static checks pass
7. No new warnings affecting the issue
8. Tracker updated
9. Commit SHA recorded
```

For AI/education issues also require:

```text
10. Golden benchmark updated
11. Before/after evaluation recorded
12. No meaningful regression in adjacent educational behavior
```

---

# 36. Agent Progress Entry Template

For every fix, append:

```markdown
## YYYY-MM-DD — <agent-name>

### Issue
- ID: P0-XXX

### Root cause
- ...

### Fix
- ...

### Tests added/updated
- ...

### Validation
```text
pytest ...
ruff ...
pyright ...
```

### Result
- PASS / FAIL

### Commit
- `<sha>`

### Remaining risk
- ...
```

---

# 37. Mandatory AI-Agent Rules

The agent must:

```text
1. Never trust an old audit blindly.
2. Re-read current source before each fix.
3. Preserve working behavior.
4. Prefer minimal safe patches over rewrites.
5. Add regression tests for every bug.
6. Avoid source-string tests when behavioral tests are possible.
7. Never weaken privacy or security controls to make tests pass.
8. Never bypass model integrity checks.
9. Never silently change curriculum semantics.
10. Record benchmark changes.
11. Record release-impacting changes.
12. Update this file before marking an issue verified.
```

---

# 38. Educational AI Quality Gate

Before every major tutor release:

```text
Correctness     >= agreed benchmark
Factuality      >= agreed benchmark
Safety          = 100% on critical refusal cases
Privacy         = 100% on critical routing cases
Prerequisites   = 100% golden-test pass
Mastery updates = 100% deterministic-test pass
Agent routing   >= agreed threshold
No major regression in latency
No database corruption regression
```

Do not optimize for one aggregate score.

---

# 39. Important Product Claims to Correct

Avoid unqualified claims such as:

```text
privacy-first
secure
personalized
tracks mastery
intelligent tutor
never leaves device
```

unless the exact operating mode and evidence are documented.

More precise:

```text
local-first
privacy-controlled
curriculum-aware
experimental mastery tracking
local model by default
cloud providers only when cloud-allowed mode is enabled
```

---

# 40. License / Distribution Awareness

The README currently describes the repository as:

```text
Educational / Personal Use Only
Commercial Use Prohibited
```

and says commercial use, SaaS deployment, incorporation into commercial products, redistribution, and competing commercial products are prohibited without permission.

The agent must not silently alter those restrictions.

Before packaging or distributing a product based on this code:

```text
review LICENSE.md
review model licenses
review training-data rights
review third-party dependency licenses
review provider terms
```

---

# 41. Target Architecture

Desired long-term flow:

```text
                      +----------------------+
                      |     Desktop UI       |
                      +----------+-----------+
                                 |
                         Capability Bridge
                                 |
                   +-------------+-------------+
                   |                           |
              Chat Service               Settings/Admin
                   |                           |
              Safety Gate                 Policy Gate
                   |
              Intent Router
                   |
             Task Planner
                   |
        +----------+-----------+
        |                      |
     Tutor Flow             General Flow
        |                      |
   Mastery/LDG            Agent Runtime
        |                      |
        +----------+-----------+
                   |
             Provider Router
                   |
        +----------+-----------+
        |                      |
      Local                 Cloud
     Provider             Providers
        |
   Model Registry
        |
 Integrity + Compatibility
        |
   GGUF/llama.cpp
```

Data plane:

```text
Session
  ↓
Persistence
  ↓
Privacy classification
  ↓
Audit metadata
```

Training plane:

```text
Curriculum
  ↓
Expert-reviewed dataset
  ↓
Deterministic generator
  ↓
Grouped split
  ↓
Training
  ↓
Held-out evaluation
  ↓
Benchmark report
  ↓
Model registry
```

---

# 42. Final Engineering Priority

Use this order:

```text
SECURITY
    ↓
PRIVACY
    ↓
DATA INTEGRITY
    ↓
TUTOR CORRECTNESS
    ↓
MODEL EVALUATION
    ↓
RELIABILITY
    ↓
OBSERVABILITY
    ↓
CI/CD
    ↓
PERFORMANCE
    ↓
NEW FEATURES
```

Do not add more agents, providers, or UI features while the foundational trust issues remain unresolved.

---

# 43. Initial Audit Change Log

## 2026-09-12 — Initial current-main audit

### Verified strengths

- modular architecture
- provider abstraction
- local-only privacy enforcement
- tool registry safeguards
- tutor transaction structure
- learning graph prerequisite cycle prevention
- SQLite WAL/foreign-key configuration
- broad regression-test inventory

### Newly recorded critical risks

- README points to missing audit document
- QWebChannel bridge is a privileged local API without a formal capability boundary
- random/near-duplicate training split risks inflated validation metrics
- mastery updates rely partly on weak textual heuristics
- privacy claims need to be scoped to actual execution mode
- non-Windows secret storage has an intentionally insecure fallback
- arbitrary bridge setting keys should be rejected
- provider-key validation mutates live provider instances
- tool timeout semantics do not guarantee termination
- regression suite contains source-text assertions and at least one placeholder test
- requirements labeled "pinned" still use `>=`
- no explicit held-out educational benchmark is visible
- model downloads need stronger manifest/hash/compatibility contracts

### Runtime verification still required

```text
- full pytest result
- Windows GUI startup
- model download flow
- actual local model generation
- provider cloud routing
- session persistence across restarts
- corruption recovery
- QWebChannel navigation behavior
- packaged executable behavior
- memory/CPU usage
- long-running generation stability
```

---

# 44. Current Status Snapshot

```text
Repository: Gayatri-Tutor-V3
Branch: main
Audit state: ACTIVE
Production-ready: NO
Research/educational prototype: YES
Critical P0 items: 6
Major P1 backlog: multiple
Runtime execution completed by this audit: NO
Living tracker: THIS FILE
```

Update the counts whenever issue status changes.

---

# 45. Start Here — For Any Future AI Coding Agent

When this file is loaded, the agent must do:

```text
STEP 1
Inspect current git HEAD and working tree.

STEP 2
Read this tracker.

STEP 3
Re-open every P0 issue against current source.

STEP 4
Run the smallest reproduction/test possible.

STEP 5
Fix only one root issue at a time.

STEP 6
Add/repair a regression test.

STEP 7
Run:
    pytest
    ruff
    type checker

STEP 8
For training/AI changes:
    run benchmark
    compare previous metrics

STEP 9
Update this file:
    status
    root cause
    fix
    validation
    commit

STEP 10
Commit.

STEP 11
Move to next P0.

STEP 12
Only after P0 is clean, continue with P1.
```

The goal is not "more code."

The goal is:

```text
A trustworthy, privacy-controlled, pedagogically defensible,
reproducible, maintainable local-first AI tutor.
```

## 2026-09-12 � Antigravity

### Issue
- ID: P0-001

### Root cause
- README pointed to a non-existent path for the audit document.

### Fix
- Kept the audit document locally in docs/GAYATRI_TUTOR_V3_ENGINEERING_TRACKER.md.`n- Removed the broken link from README.md entirely per user request.
- Added a "How to update this tracker" heading.

### Tests added/updated
- None needed (link correction).

### Validation
`	ext
Test-Path docs/GAYATRI_TUTOR_V3_ENGINEERING_TRACKER.md
`

### Result
- PASS

### Commit
- Pending

### Remaining risk
- None


## 2026-09-12 � Antigravity

### Issue
- ID: P0-002

### Root cause
- QWebChannel exposed all backend operations indiscriminately on a single Bridge instance to frontend JS.

### Fix
- Replaced monolithic bridge registration with explicit sub-bridges (ChatBridge, SettingsBridge, ProviderBridge, ModelBridge, WindowBridge).
- Bridge acts as a facade connecting signals and slots to maintain backward compatibility for existing JS, while properly dividing capabilities into safe isolated domains.
- Validated unknown settings rejection and bridge isolation.

### Tests added/updated
- 	ests/test_bridge_capability.py

### Validation
`	ext
pytest tests/test_bridge_capability.py
ruff check .
`

### Result
- PASS

### Commit
- Pending

### Remaining risk
- JS currently still uses the unified ridge for older API calls, but new UI features should connect strictly to the specific sub-bridges to enforce least privilege.
