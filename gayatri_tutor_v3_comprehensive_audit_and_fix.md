
# 🚨 CALL FOR CONTRIBUTORS 🚨

**We need your help!** This comprehensive audit has identified 73 issues that need fixing. 
We are calling on the open-source community on GitHub to help us resolve these. 
If you would like to contribute, please pick an issue marked with **[HELP WANTED]**, create a fork, and submit a Pull Request!

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

# Gayatri Tutor V3 — Comprehensive Bug, Dead-End, Silent-Failure & Conditional-Failure Audit

## Repository

Repository: `Gayatri-Education/Gayatri-Tutor-V3`

Branch audited: `main`

Audit target: current repository state available at the time this document was generated.

## Purpose

This document is an engineering task specification for a local AI coding agent.

The agent must:

1. inspect the current repository before changing anything;
2. independently verify every issue below against the current code;
3. fix confirmed issues;
4. add regression tests;
5. preserve intended architecture and educational behavior;
6. update documentation when behavior changes;
7. run the complete test/lint suite;
8. create a dedicated branch;
9. commit the fixes;
10. push the branch;
11. raise a Pull Request against `main`.

Do **not** blindly apply findings from this document. The repository already contains a `BUGS.md` and some previously reported issues have been fixed since that report. The agent must distinguish:

- confirmed current bugs;
- already-fixed historical bugs;
- conditional/runtime-dependent bugs;
- design limitations;
- dead code;
- misleading documentation;
- test gaps.

---

# 1. Severity Definitions

## P0 — Critical

A defect that can:

- prevent the application from starting;
- make a primary feature unusable;
- corrupt persisted state;
- expose sensitive data;
- cause incorrect educational/mastery behavior;
- cause an unrecoverable or highly confusing user workflow.

## P1 — High

A defect that:

- silently produces wrong behavior;
- causes a major feature to fail under common conditions;
- creates a privacy/security risk;
- causes incorrect routing/model selection;
- creates persistent state corruption;
- makes advertised functionality materially unreliable.

## P2 — Medium

A defect that:

- breaks a secondary feature;
- causes misleading UI/status;
- creates inconsistent behavior;
- produces avoidable resource usage;
- weakens robustness or maintainability.

## P3 — Low

A correctness edge case, dead code path, documentation mismatch, weak test, or maintainability issue that does not normally block the application.

---

# 2. Important Baseline Observation

The repository's existing `BUGS.md` reports 24 historical issues. Several of those have already been fixed in the current tree.

The local agent MUST NOT reintroduce them or treat them as unresolved merely because they appear in `BUGS.md`.

### Historical issues that appear already fixed and should be verified, not blindly reworked

- Ollama model progress callback signature.
- Missing `json` import in Anthropic provider.
- PII replacement offset corruption.
- Streaming PII redaction.
- Local model stop token.
- Tutor prerequisite metadata key mismatch.
- Tutor recent-attempt context plumbing.
- Chat assistant placeholder creation.
- Token joining with injected spaces.
- `pyproject.toml` build backend.
- `pyproject.toml` optional dependency spelling.
- Several dependency declarations/RAG changes.
- Windows RAM detection.
- Mastery threshold lookup.
- Session title update.
- Prerequisite cycle detection.
- Single-word agent trigger penalty.
- Concurrent `send_message()` guard.

The agent should add/retain regression tests for these fixes where tests are weak.

---

# 3. P0 — [HELP WANTED] Tutor Mastery Assessment Is Fundamentally Unsafe

## File

`core/orchestrator.py`

## Location

`_evaluate_tutor_response()`

## Problem

The tutor evaluates student answers using simplistic string/length heuristics:

```python
if len(lower_msg) < 3:
    correct = False
elif lower_msg in ("i don't know", "idk", "?", "help", "i'm stuck", "no idea"):
    correct = False
elif lower_msg.startswith(("yes", "yeah", "yep", "correct", "right", "i think", "it is")):
    correct = True
elif lower_msg.startswith(("no", "nope", "wrong", "incorrect", "not")):
    correct = False
elif len(lower_msg) > 20:
    correct = True
else:
    correct = True
```

This means a long but completely wrong answer is automatically classified as correct.

A short but correct mathematical/programming answer can be classified incorrectly.

A student can therefore accumulate mastery simply by writing sufficiently long text.

## Impact

This directly corrupts the Learning Dependency Graph.

The system can:

```text
wrong answer
    ↓
correct=True
    ↓
mastery increases
    ↓
concept becomes "mastered"
    ↓
prerequisite becomes unlocked
    ↓
student is advanced to harder material
```

This defeats the central educational purpose of the LDG.

## Required fix

Do not pretend a heuristic can reliably assess correctness.

Choose one of these architectures:

### Preferred

Introduce an explicit assessment layer that returns:

```text
correct
incorrect
uncertain
```

with an assessment confidence.

For example:

```python
AssessmentResult(
    status="uncertain",
    confidence=0.42,
    rationale="The response contains an attempt but cannot be reliably evaluated."
)
```

If the system is intentionally privacy-first/local-only, the local model can perform assessment using a dedicated structured prompt.

### Minimum safe behavior

If correctness cannot be established confidently:

```text
DO NOT increase mastery.
```

An uncertain response should not count as correct.

## Regression tests

Test:

- clearly correct answer;
- clearly incorrect answer;
- long incorrect answer;
- short correct answer;
- "I don't know";
- ambiguous answer;
- answer with code;
- mathematical expression;
- multilingual answer.

Required invariant:

> An uncertain answer must never increase mastery as if it were correct.

---

# 4. P0 — [HELP WANTED] PII Restore Is Incorrect When Multiple Values Share a Placeholder

## File

`core/privacy.py`

## Problem

Redaction now correctly uses `pattern.sub()`, but every email becomes:

```text
[EMAIL]
```

and every phone number becomes:

```text
[PHONE_IN]
```

The restore implementation does:

```python
for r in self.redactions:
    result = result.replace(r.placeholder, r.original)
```

Example:

```text
Input:
Contact alice@example.com and bob@example.com

Redacted:
Contact [EMAIL] and [EMAIL]
```

Restore:

```text
replace("[EMAIL]", "alice@example.com")
```

produces:

```text
Contact alice@example.com and alice@example.com
```

The second replacement has no way to distinguish the second original value.

## Impact

Any feature that relies on restoring redacted text can silently substitute one user's PII for another.

## Required fix

Use unique placeholders per occurrence, for example:

```text
[EMAIL_1]
[EMAIL_2]
```

or use an indexed token representation.

The restore function must be deterministic and one-to-one.

## Tests

Test:

- two emails;
- two phone numbers;
- mixed PII;
- repeated identical PII;
- PII adjacent to punctuation;
- placeholder-like user input;
- restore after model-generated text containing placeholders.

Also ensure a user cannot inject a placeholder string that causes unintended restoration.

---

# 5. P0 — [HELP WANTED] Placeholder Injection / PII Restore Integrity

## File

`core/privacy.py`

## Problem

The model receives placeholders such as:

```text
[EMAIL]
```

If restore is performed by global string replacement, a model-generated response containing the same placeholder text can accidentally cause PII restoration.

Example:

```text
User:
My email is alice@example.com.

Model:
Please write [EMAIL] in the assignment.
```

A naive restore can produce:

```text
Please write alice@example.com in the assignment.
```

## Required fix

Do not use global unrestricted string replacement.

Use unique, cryptographically/randomly hard-to-guess placeholders or a structured restoration mechanism that restores only placeholders originally inserted by the redactor.

## Test

Prove that model-generated placeholder-like text is not restored unless it corresponds to a real redaction token.

---

# 6. P0 — [HELP WANTED] "Privacy First" Is Not Equivalent to "No Data Leaves the Device"

## Files

- `core/orchestrator.py`
- cloud provider implementations
- provider registry
- UI/provider settings

## Problem

The README describes the application as local-first/privacy-first, while the code includes cloud providers and API-key storage.

A user may configure a cloud provider and assume the same privacy guarantees apply.

The system needs an explicit privacy state.

## Required behavior

Every request should have a clear execution mode:

```text
LOCAL_ONLY
CLOUD_PROVIDER
MIXED
```

The UI must make it obvious when a prompt will leave the device.

If privacy mode is intended to prevent cloud calls, enforce it rather than merely describing it.

## Tests

- local-only mode never invokes cloud provider;
- cloud-enabled mode is explicit;
- provider selection cannot silently switch from local to cloud;
- errors do not trigger an unexpected cloud fallback.

---

# 7. P0 — [HELP WANTED] Secrets Vault Must Fail Closed on Non-Windows

## File

`core/security/secrets.py`

## Problem

Non-Windows platforms intentionally fall back to base64 encoding.

Base64 is not encryption.

The code documents this, but the broader application calls the feature a secure secrets vault.

This creates a conditional security failure if the application is ever run outside Windows.

## Required fix

Preferred:

- require a real OS-backed secret store on non-Windows;
- or refuse to persist secrets and provide an explicit "unsupported secure storage" status.

Do not silently store API keys using reversible encoding.

If the educational project intentionally supports insecure development fallback, it must require an explicit opt-in such as:

```text
ALLOW_INSECURE_SECRET_STORAGE=true
```

and clearly warn the user.

## Tests

- Windows DPAPI path;
- non-Windows secure-store path;
- non-Windows insecure fallback disabled by default;
- no plaintext/base64 secret written without explicit opt-in.

---

# 8. P1 — [HELP WANTED] Secret Vault Loses Keys Silently When One Entry Is Corrupt

## File

`core/security/secrets.py`

## Problem

`_load_vault()` catches decryption errors for individual keys, logs the error, and skips the entry.

This means:

```text
secrets.enc
  ├── openai
  ├── anthropic
  └── google

anthropic corrupt
        ↓
load_vault()
        ↓
openai + google returned
anthropic silently missing
```

The user may think the API key was deleted.

## Required fix

Return structured vault health information.

Distinguish:

```text
NO_KEY
KEY_PRESENT
KEY_CORRUPTED
VAULT_CORRUPTED
```

Do not silently downgrade corruption to absence.

---

# 9. P1 — [HELP WANTED] Atomic Vault Writes Need Crash-Safe Semantics

## File

`core/security/secrets.py`

## Problem

The implementation writes a temporary file and replaces the final file, which is good, but does not explicitly ensure:

- file flushing;
- OS-level durability;
- cleanup of abandoned temporary files;
- concurrent writer protection.

## Required fix

At minimum:

- lock vault writes;
- flush/fsync where appropriate;
- remove abandoned temp files safely;
- ensure concurrent `store_key()` calls cannot lose each other's updates.

## Important race

Two threads can execute:

```text
Thread A: load vault
Thread B: load vault
Thread A: add key A
Thread B: add key B
Thread A: save
Thread B: save
```

Result:

```text
key A lost
```

Add a lock around load-modify-save operations.

---

# 10. P1 — [HELP WANTED] Tutor State Is In-Memory and Can Be Lost Between Sessions

## File

`core/tutor_engine.py`

## Problem

`tutor_engine.py` stores:

```python
session_contexts: dict[str, TutorContext]
```

in memory.

The normal chat session is persisted to SQLite, but TutorContext is not obviously persisted alongside the session.

A restart can therefore lose:

- current concept;
- waiting-for-answer state;
- last answer status;
- subject;
- response type.

## Impact

A student may restart the app and receive a different teaching state despite having persistent chat history.

## Required fix

Persist tutor state or deterministically reconstruct it from persisted learning state.

At minimum persist:

```text
session_id
current_concept_id
subject
waiting_for_answer
last_response_type
```

Do not persist transient secrets.

## Tests

Restart/recreate TutorEngine and verify state restoration.

---

# 11. P1 — [HELP WANTED] Global LDG and TutorEngine Instances Can Create Cross-Session Coupling

## Files

- `core/orchestrator.py`
- `core/tutor_engine.py`

## Problem

The orchestrator uses global:

```text
_ldg
_tutor_engine
_conversations
```

and TutorEngine stores all session contexts in one mutable dictionary.

This is acceptable for a single-user desktop application only if concurrency is strictly controlled.

It becomes fragile when:

- multiple windows exist;
- multiple threads process turns;
- tests run in parallel;
- future multi-user/server use is attempted.

## Required fix

Document single-user/thread assumptions or introduce explicit synchronization.

Prefer dependency injection of session state where practical.

---

# 12. P1 — [HELP WANTED] AgentRuntime Tool Loop Needs Stronger Safety Boundaries

## File

`core/agents/runtime.py`

## Current behavior

The tool loop catches tool errors and feeds the error string back into the model.

## Problems

### A. Tool errors become model input

An exception can contain implementation details or sensitive information.

### B. Unknown tools are model-visible errors

The model can repeatedly request an invalid tool.

### C. Tool call count is limited, but no time/resource budget exists

A tool can hang or consume significant resources.

### D. Tool arguments are not schema-validated

`ToolRegistry.call()` accepts arbitrary `**kwargs`.

## Required fix

Add:

- tool schemas;
- argument validation;
- per-tool timeout;
- total execution timeout;
- maximum tool-call count;
- safe user-facing errors;
- sanitized model-facing errors;
- audit logging without secret values.

---

# 13. P1 — [HELP WANTED] Tool Registry Is Global and Mutable

## File

`core/agents/runtime.py`

## Problem

```python
tool_registry = ToolRegistry()
```

is global mutable state.

A plugin or agent can register/replace a tool name.

A duplicate registration silently overwrites the previous implementation.

## Required fix

Reject duplicate registrations unless explicit replacement is requested.

Add:

```python
ToolSpec(
    name,
    description,
    argument_schema,
    timeout,
    permission
)
```

where appropriate.

---

# 14. P1 — [HELP WANTED] Agent Selection Can Still Misroute Despite Single-Word Penalty

## Files

- `core/agents/registry.py`
- `core/agents/prompt_agents.py`

## Problem

Single-word triggers are now multiplied by `0.5`, but this is still heuristic routing.

Many generic triggers overlap:

```text
news
schedule
design
support
sales
research
finance
etc.
```

A partial overlap can win against a more semantically appropriate agent.

## Required fix

Add:

- minimum confidence margin;
- tie handling;
- generic/default agent fallback;
- explicit command priority;
- deterministic tests for ambiguous prompts.

Example:

```text
best score = 0.62
second score = 0.61

→ do not confidently route.
```

Use a fallback/general agent.

## Tests

Create an ambiguity matrix with realistic user questions.

---

# 15. P1 — [HELP WANTED] Agent Trigger Matching Uses Set Intersection and Loses Phrase Semantics

## File

`core/agents/registry.py`

## Problem

The matcher converts both trigger and input to sets of words.

This loses:

- word order;
- repeated words;
- phrase boundaries;
- negation;
- context.

For example, triggers containing:

```text
"not financial advice"
```

are treated as an unordered word set.

## Required fix

Use a layered matcher:

1. exact command;
2. exact phrase;
3. normalized phrase;
4. token similarity;
5. optional semantic routing.

Do not let a weak token overlap outrank a strong phrase match.

---

# 16. P1 — [HELP WANTED] `_local_chat()` Converts Model Failure Into a Plausible Success Message

## Files

- `core/agents/default_agents.py`
- `core/agents/prompt_agents.py`

## Problem

Both modules catch all exceptions and return:

> "I'm running without the local model right now..."

This is returned as an ordinary `AgentResponse.text`.

The orchestrator may then persist this as a normal assistant answer.

## Impact

A hard model failure becomes a successful-looking assistant response.

This makes operational failures difficult to detect.

## Required fix

Return structured failure state:

```python
AgentResponse(
    text="...",
    status="MODEL_UNAVAILABLE",
    metadata={...}
)
```

or raise a typed exception that the UI handles.

The UI should distinguish:

```text
normal model response
model unavailable
provider error
tool error
```

---

# 17. P1 — [HELP WANTED] Orchestrator Persists Error Text as Assistant Conversation Content

## File

`core/orchestrator.py`

## Problem

Streaming fallback:

```python
error_text = f"[Error: {exc}]"
buffer.append(error_text)
yield error_text, True
```

Then the accumulated buffer is stored as an assistant message.

This contaminates conversation history with implementation/runtime errors.

## Required fix

Do not persist infrastructure errors as assistant responses.

Instead:

```text
conversation:
user message

UI:
error state
```

If a retry message is needed, store it as metadata/event rather than model content.

## Test

Force a provider failure and verify persisted conversation does not contain raw exception text.

---

# 18. P1 — [HELP WANTED] Orchestrator Emits Completion More Than Once on Some Paths

## Files

- `core/orchestrator.py`
- `app/bridge.py`

## Problem

The streaming path can yield:

```text
error_text, True
```

and later:

```text
"", True
```

The bridge emits `done()` for every `is_done`.

This can trigger duplicate completion handling and session saves.

## Required fix

Guarantee exactly one terminal event:

```text
TOKEN*
DONE | ERROR
```

not multiple `DONE` events.

Define a small stream event protocol.

---

# 19. P1 — [HELP WANTED] Error Messages Can Leak Internal Paths and Implementation Details

## Files

- `core/orchestrator.py`
- `app/bridge.py`
- provider implementations

## Problem

Examples include:

```python
str(exc)
```

being sent directly to UI.

Errors can include:

- local file paths;
- provider URLs;
- model paths;
- internal implementation details;
- configuration values.

## Required fix

Separate:

```text
internal_error
user_message
diagnostic_id
```

Log full details locally, but show sanitized messages to users.

---

# 20. P1 — [HELP WANTED] Provider Registry Treats Fallback Model Catalogs as Available

## File

`core/providers/google.py`

## Problem

If the Google API model-list request fails, `list_models()` falls back to hardcoded known models.

Then `ProviderRegistry._check_provider_available()` calls `list_models()` and can conclude the provider is available because the fallback list is non-empty.

This conflates:

```text
provider reachable
```

with:

```text
we know about provider model IDs
```

## Impact

UI may show Google as available when the network/key/API is actually unavailable.

## Required fix

Separate:

```text
catalog_source = LIVE | FALLBACK
reachable = true/false
authenticated = true/false
```

The fallback catalog must not imply successful connectivity.

---

# 21. P1 — [HELP WANTED] Cloud Model Catalogs Are Hardcoded and Can Become Stale

## Files

- `core/providers/google.py`
- `core/providers/anthropic.py`

## Problem

Provider model lists contain hardcoded IDs.

LLM providers retire, rename, or change model IDs.

The application may display models that no longer exist.

## Required fix

Prefer live provider model discovery.

Keep fallback models only as clearly marked compatibility data.

Add model validation before first use.

Do not silently retry a retired model indefinitely.

---

# 22. P1 — [HELP WANTED] Google Provider Claims Tool Support but Tool Calls Are Not Actually Converted

## File

`core/providers/google.py`

## Problem

The provider advertises:

```python
supports_tools() -> True
```

and model metadata can indicate tool support.

But `_convert_messages()` converts `tool` messages to plain user text:

```text
[Tool result: ...]
```

and `chat()` does not appear to construct Gemini's native tool declarations/function-calling request from `opts.tools`.

## Impact

A feature may be advertised as supported while tool execution is not actually wired through.

## Required fix

Either:

1. implement actual Google function/tool calling; or
2. return `supports_tools() == False`.

Do not advertise unsupported capability.

## Tests

Mock a tool-call request and verify provider request payload.

---

# 23. P1 — [HELP WANTED] Anthropic Provider's JSON Mode May Not Match the Actual API Contract

## File

`core/providers/anthropic.py`

## Problem

The provider advertises JSON support and sends:

```python
response_format={"type": "json_object"}
```

The implementation must be verified against the exact Anthropic API contract used by the project.

## Required fix

Do not claim JSON mode unless the request format is supported by the targeted API/model.

If unsupported, implement prompt-based structured output or remove the capability flag.

## Tests

Mock/contract-test the request payload.

---

# 24. P1 — [HELP WANTED] Provider Model Selection Ignores User Model Selection

## Files

- provider implementations;
- `core/orchestrator.py`;
- settings/UI/provider registry.

## Problem

`TurnOptions` contains:

```python
model_override
forced_tier
```

but the direct local fallback in `Orchestrator.submit()` and `stream()` calls:

```python
LocalProvider.chat(...)
```

without using `model_override`.

This means a caller can provide model-selection options that have no effect.

## Required fix

Either wire options through the entire routing pipeline or remove unused options.

Every accepted configuration option must have observable behavior.

---

# 25. P1 — [HELP WANTED] `TurnOptions.task_type` Appears Unused

## File

`core/orchestrator.py`

## Problem

`task_type` is declared but does not appear to influence routing.

This creates a false API contract.

## Required fix

Implement it or remove it.

Add a test for every supported `TurnOptions` field.

---

# 26. P1 — [HELP WANTED] Provider Registry Fallback Chain Can Select a Provider That Is Not Actually Ready

## File

`core/providers/registry.py`

## Problem

`get_fallback_chain()` uses `list_models()` as a proxy for availability.

A fallback catalog can make a dead provider look usable.

## Required fix

Use explicit provider health/authentication state.

A provider should enter the execution fallback chain only if:

```text
reachable + authenticated + model available
```

or equivalent.

---

# 27. P1 — [HELP WANTED] Settings Schema Does Not Validate Semantic Ranges

## File

`core/settings.py`

## Problem

The schema validates Python types but not meaningful ranges.

Examples:

```text
temperature = -100
max_tokens = -1
theme = "banana"
router_preference = "unknown"
```

can pass type checks.

## Required fix

Add semantic validation:

```text
temperature: 0..2
max_tokens: positive bounded integer
theme: dark/light
router_preference: known enum
```

Use configuration constants rather than magic limits where possible.

## Tests

Test invalid ranges and enum values.

---

# 28. P1 — [HELP WANTED] Settings Accept Unknown Keys Without Warning

## File

`core/settings.py`

## Problem

Unknown settings are silently accepted:

```python
self._settings[key] = value
```

This can hide UI/configuration typos.

## Required fix

Either:

- reject unknown keys; or
- explicitly support extension keys under a namespace.

At minimum log a warning for unknown keys.

---

# 29. P2 — [HELP WANTED] Settings File Does Not Explicitly Define Encoding

## File

`core/settings.py`

## Problem

Files are opened without explicit UTF-8 encoding.

On some environments this can cause non-ASCII settings to behave differently.

## Fix

Use:

```python
encoding="utf-8"
```

for text file operations.

---

# 30. P1 — [HELP WANTED] Session Save Rewrites All Messages on Every Save

## File

`core/session.py`

## Problem

`save_session()` deletes all messages for the session and reinserts them.

This is simple but creates risks:

- unnecessary writes;
- potential data loss if process crashes between delete and commit;
- poor scalability;
- message IDs/timestamps may be recreated.

## Required fix

Prefer transactional upsert/append semantics.

If full replacement is retained, ensure it is a single transaction and test crash/rollback behavior.

---

# 31. P1 — [HELP WANTED] Session Persistence and Active Conversation Can Diverge

## Files

- `core/session.py`
- `app/bridge.py`
- `core/orchestrator.py`

## Problem

The session is only explicitly saved through bridge operations such as `_save_current_session()`.

A process crash during an active conversation can lose the most recent turns.

## Required fix

Consider autosaving after each completed turn or at controlled intervals.

At minimum, document the persistence guarantee.

---

# 32. P1 — [HELP WANTED] Session Loading Does Not Restore Tutor State

## Files

- `app/bridge.py`
- `core/orchestrator.py`
- `core/tutor_engine.py`

## Problem

The app can load chat messages, but TutorEngine state is separate.

A loaded conversation may visually show the previous discussion while the tutor engine thinks:

```text
new concept
not waiting for answer
default mastery context
```

## Required fix

Persist and restore teaching state or reconstruct it.

Add an integration test for:

```text
chat → save → restart → load → tutor continuation
```

---

# 33. P1 — [HELP WANTED] Learning Path Cycle Detection Is Correct at Insert Time but Path Generation Should Still Detect Corruption

## File

`core/knowledge_graph.py`

## Problem

`add_prerequisite()` now checks cycles, which is good.

But the database itself can still be externally modified, migrated, or corrupted.

`get_learning_path()` should not silently append the goal after a failed topological sort.

## Required fix

If the number of sorted nodes is less than the expected ancestor set:

```text
raise/return explicit cycle error
```

rather than silently returning an incomplete path.

---

# 34. P1 — [HELP WANTED] LDG Subject Filtering Can Produce Empty/Unexpected Progress

## File

`core/knowledge_graph.py`

## Problem

Tutor context has a subject field, but the default subject appears to be empty.

A future subject-specific curriculum can therefore produce unexpected cross-subject selection.

## Required fix

Define subject lifecycle explicitly:

```text
current subject
curriculum subject
fallback behavior
```

Do not silently mix concepts from unrelated subjects.

---

# 35. P1 — [HELP WANTED] Mastery Updates Ignore Assessment Confidence

## Files

- `core/orchestrator.py`
- `core/tutor_engine.py`
- `core/knowledge_graph.py`

## Problem

`record_student_response()` accepts `confidence`, but orchestrator calls it without passing a meaningful assessment confidence.

Thus the default is effectively full confidence.

## Required fix

Connect:

```text
assessment confidence
        ↓
mastery update
```

For uncertain assessment, use a lower confidence or no update.

---

# 36. P2 — [HELP WANTED] Mastery Progression Can Be Overly Sensitive to Repeated Correct Answers

## File

`core/knowledge_graph.py`

## Problem

Mastery is updated with an exponential moving approach.

The model should verify that:

- a single lucky answer cannot instantly unlock a concept;
- repeated shallow answers cannot artificially reach mastery;
- difficulty is considered where appropriate.

This is a design/educational correctness review, not necessarily a pure bug.

## Required action

Add tests around threshold behavior and document the intended mastery model.

---

# 37. P1 — [HELP WANTED] Conversation History Can Exceed Intended Context Semantics

## Files

- `core/conversation.py`
- `core/orchestrator.py`

## Problem

Conversation stores a fixed number of messages, while orchestrator uses:

```text
last 10 messages
```

This is message-count based rather than token-count based.

Long messages can exceed the model context despite the comment claiming token-limit awareness.

## Required fix

Implement token-aware truncation where practical.

At minimum:

- bound characters/tokens;
- preserve system instructions;
- preserve the current turn;
- trim oldest context first.

---

# 38. P1 — [HELP WANTED] Conversation Trimming Can Destroy Turn Pairing

## File

`core/conversation.py`

## Problem

The trim operation keeps the last N individual user/assistant messages.

If N cuts between a user message and its assistant response, the model can receive an orphaned assistant response.

## Required fix

Trim by conversation turns:

```text
user + assistant
```

rather than arbitrary individual messages.

System messages should remain first.

## Test

Add enough messages to force trimming and assert no orphan assistant messages are produced.

---

# 39. P2 — [HELP WANTED] Conversation Timestamp Semantics Are Inconsistent During Persistence

## Files

- `core/conversation.py`
- `core/session.py`

## Problem

Messages created in memory have timestamps, while `save_session()` can substitute `now` when timestamps are absent.

Ensure loaded/persisted messages preserve original timestamps.

---

# 40. P1 — [HELP WANTED] Model Download Resume Can Corrupt a Partial File If Server Ignores Range

## File

`core/model_fetch/ollama_pull.py`

## Problem

If a partial file exists, the client sends:

```text
Range: bytes=<downloaded>-
```

If the server responds with `200` full content, the code correctly switches to `"wb"` and resets downloaded.

That is good.

However, if a server returns an unexpected `206` range that does not start at the requested offset, the code should verify the content-range start.

## Required fix

Validate:

```text
Content-Range start == existing downloaded size
```

before appending.

If not, restart safely.

---

# 41. P1 — [HELP WANTED] Model Download Cancellation Leaves a Partial File That Looks Like a Valid Installation Candidate

## Files

- `core/model_fetch/ollama_pull.py`
- `app/bridge.py`

## Problem

Cancellation raises an error during chunk processing.

The partial model file remains.

`install_model()` only checks whether the file exists and reports:

```text
installed
```

without verifying size/digest.

## Impact

A cancelled/failed download can be reported as installed.

## Required fix

Installation status must be based on:

```text
file exists
AND
file is structurally valid
AND
digest is known/verified
```

Do not treat file existence as successful installation.

## Test

Create a partial file and verify status is not `installed`.

---

# 42. P1 — [HELP WANTED] `latest` Model Tag Is Not Reproducible

## File

`core/model_fetch/ollama_pull.py`

## Problem

Default model tag is:

```text
latest
```

A user can download different model content on different dates.

## Required fix

Persist:

```text
resolved digest
model tag
download timestamp
```

and preferably use a pinned digest/version for reproducible releases.

---

# 43. P1 — [HELP WANTED] Model File Path and Model Identity Can Drift

## Files

- `core/config.py`
- `core/providers/local.py`
- `app/bridge.py`

## Problem

The UI reports a hardcoded model name:

```python
"name": "gemma-2-2b-it"
```

while the downloader uses:

```text
DBERT/DBERT_AI:latest
```

and the local model path is configuration-driven.

This can produce a UI that says one model is installed while another model is actually present.

## Required fix

The installed model status must report the actual:

```text
model family
model name
version/tag
digest
path
size
```

from metadata, not a hardcoded string.

---

# 44. P1 — [HELP WANTED] Model Download Digest Is Not Persisted as Installation Metadata

## Problem

The downloader verifies the digest but does not clearly persist the verified identity alongside the model.

## Required fix

Store a small metadata file:

```json
{
  "namespace": "...",
  "name": "...",
  "tag": "...",
  "digest": "...",
  "verified_at": "..."
}
```

Do not store secrets.

---

# 45. P2 — [HELP WANTED] Hardware GPU Detection Only Uses NVIDIA

## File

`core/hardware.py`

## Problem

The README/project targets desktop users broadly, but hardware detection only actively detects NVIDIA CUDA through `nvidia-smi`.

AMD/Intel/Apple GPU systems become CPU-only from the application's perspective.

## Required action

Either:

- implement supported alternatives;
- or document NVIDIA-only GPU acceleration clearly.

Do not claim general hardware acceleration if it is not supported.

---

# 46. P2 — [HELP WANTED] Hardware Recommendation Uses Rough GPU Layer Heuristics

## File

`core/hardware.py`

## Problem

The formula:

```text
(vram/model_size) * 35
```

is a rough estimate.

Actual layer memory depends on:

- architecture;
- quantization;
- context;
- KV cache;
- runtime overhead.

## Required action

Do not represent this as a guaranteed safe configuration.

Add a fallback if model initialization fails with out-of-memory.

---

# 47. P1 — [HELP WANTED] Local Model Singleton Is Not Thread-Safe

## File

`core/providers/local.py`

## Problem

`LocalProvider._model` is a global class-level singleton.

Concurrent calls can race during:

```text
_load_model()
```

and generation.

## Required fix

Add a lock around model initialization and, if llama.cpp usage requires it, around inference.

The bridge currently blocks overlapping UI requests, but other callers/tests may still access the provider concurrently.

---

# 48. P2 — [HELP WANTED] Local Model `health()` Can Trigger a Heavy Model Load

## File

`core/providers/local.py`

## Problem

`health()` calls `_load_model()`.

A UI status check can therefore:

```text
health check
  ↓
load hundreds of MB/GB
  ↓
allocate RAM/VRAM
  ↓
block UI/backend
```

A health check should not unexpectedly perform a heavy initialization unless explicitly requested.

## Required fix

Separate:

```text
installed
loadable
loaded
ready
```

and make "probe by loading" explicit.

---

# 49. P1 — [HELP WANTED] UI Error Handling Swallows Exceptions

## File

`app/ui/index.html`

## Problem

`updateModelStatus()` does:

```javascript
catch(e) {}
```

This is a silent failure.

If the QWebChannel is not ready or the bridge returns invalid JSON, the UI simply remains in an ambiguous state.

## Required fix

Show:

```text
Status unavailable
```

and log a useful diagnostic.

Never use an empty catch for critical UI initialization.

---

# 50. P1 — [HELP WANTED] Sidebar Tabs Remain Non-Functional

## File

`app/ui/index.html`

## Problem

`switchTab(tab)` only changes the active icon.

There are no corresponding Agents/Courses/Settings content panels.

This is a visible dead-end.

## Required fix

Either implement the panels or remove/disable the controls until implemented.

A clickable UI control must not pretend to work.

---

# 51. P1 — [HELP WANTED] `switchTab()` Depends on Global `event`

## File

`app/ui/index.html`

## Problem

The function uses:

```javascript
event.target
```

without receiving `event`.

This relies on browser-specific global event behavior.

## Required fix

Use:

```javascript
onclick="switchTab('chat', event)"
```

and:

```javascript
function switchTab(tab, event) { ... }
```

or use `this`.

---

# 52. P1 — [HELP WANTED] Agent Selector Is Dead UI Unless Populated

## File

`app/ui/index.html`

## Problem

The UI contains:

```html
<select id="agentSelect">
  <option value="auto">Auto-detect</option>
</select>
```

but the current frontend must be verified for population and whether selected agents affect routing.

If no bridge call populates/uses the selector, it is dead UI.

## Required action

Either:

- populate it from the registry and wire selection to routing;
- or remove it.

Do not expose a control whose value is ignored.

---

# 53. P1 — [HELP WANTED] User Can Send Before QWebChannel Is Ready

## File

`app/ui/index.html`

## Problem

`bridge` begins as `null`.

The input/button is still present immediately.

A user can potentially click Send before the QWebChannel callback completes.

## Required fix

Disable input/send until:

```text
bridge != null
```

Then enable it.

## Test

Simulate/verify early interaction.

---

# 54. P1 — [HELP WANTED] UI Can Display a Successful Model State While Model Is Not Actually Loaded

## Files

- `app/bridge.py`
- `app/ui/index.html`
- `core/providers/local.py`

## Problem

The distinction between:

```text
model file installed
```

and:

```text
model successfully loaded
```

needs to be explicit.

The UI currently uses `installed` as the main readiness indicator.

## Required fix

Expose:

```text
installed
valid
loaded
ready
reason_code
```

and render them separately.

---

# 55. P1 — [HELP WANTED] Model Status UI Hardcodes Gigabyte Display

## File

`app/ui/index.html`

## Problem

The UI computes:

```javascript
status.size_mb / 1024
```

and labels the result GB.

This is not a functional bug, but small models can display awkward values and the hardcoded model name is misleading.

Use a generic formatter.

---

# 56. P2 — [HELP WANTED] No User-Facing Retry State for Failed Generation

## Files

- `app/ui/index.html`
- `app/bridge.py`

## Problem

On provider/model failure, the UI receives a generic error message.

There is no structured retry state.

## Required improvement

Expose:

```text
retryable
error_code
message
```

and provide a Retry action when appropriate.

---

# 57. P1 — [HELP WANTED] Model Download Progress Uses Qt Signals From a Worker Thread

## File

`app/bridge.py`

## Problem

A Python `threading.Thread` directly calls Qt signals.

This often works because Qt signals are thread-aware, but the lifecycle and QObject affinity should be verified carefully.

## Required action

Prefer Qt `QThread`/worker patterns for long-running Qt operations if current implementation shows instability.

At minimum add integration tests around:

- progress;
- cancellation;
- completion;
- window close during download.

---

# 58. P1 — [HELP WANTED] Window Close During Background Download Needs Lifecycle Handling

## Files

- `app/bridge.py`
- `app/windows/main_window.py`

## Problem

The model downloader uses:

```python
threading.Thread(..., daemon=True)
```

The window can close while the worker is writing a large model.

## Risks

- incomplete file;
- corrupted installation;
- callbacks targeting destroyed Qt objects.

## Required fix

Define shutdown behavior:

```text
close requested
↓
cancel active download
↓
wait or detach safely
↓
close UI
```

---

# 59. P1 — [HELP WANTED] File Downloads Need Disk-Space Preflight

## File

`core/model_fetch/ollama_pull.py`

## Problem

The manifest provides blob size, but the downloader does not appear to preflight:

```text
available disk space
```

A nearly-full disk can produce a partial file and late failure.

## Required fix

Before download:

```text
required bytes + safety margin <= available bytes
```

Return a clear error.

---

# 60. P2 — [HELP WANTED] Download Uses Synchronous HTTP API Inside Worker but Lacks Retry Strategy

## File

`core/model_fetch/ollama_pull.py`

## Problem

A single transient network interruption can fail a large model download.

The code supports resume but not robust retry/backoff.

## Required fix

Add bounded retries for transient failures.

Do not retry:

- digest mismatch indefinitely;
- authentication errors;
- invalid manifest;
- unsupported status codes.

---

# 61. P1 — [HELP WANTED] Model Download Progress Can Report Unknown Total as 0 MB Total

This is mostly UX, but it can create division/percentage ambiguity.

Ensure UI explicitly shows:

```text
Downloading X MB
```

when total is unknown rather than implying a complete percentage.

---

# 62. P1 — [HELP WANTED] API Key Validation Temporarily Mutates Shared Provider State

## File

`app/bridge.py`

## Problem

`validate_provider_key()` does:

```python
old_key = provider._api_key
provider._api_key = api_key
valid, msg = provider.validate_key()
provider._api_key = old_key
```

If another thread uses the provider simultaneously, it can accidentally use the temporary key.

## Required fix

Do not mutate shared provider state for validation.

Create a temporary provider instance or make validation accept a key argument.

## Test

Run concurrent validation and inference operations.

---

# 63. P2 — [HELP WANTED] Provider Key Save Does Not Validate Before Persisting

## File

`app/bridge.py`

## Problem

`save_provider_key()` directly stores the key.

A typo can be persisted.

## Required behavior

Prefer:

```text
validate
  ↓
save
```

or explicitly allow "save without validation" with clear UI status.

---

# 64. P1 — [HELP WANTED] Cloud API Keys Are Included in URLs for Google

## File

`core/providers/google.py`

## Problem

Requests use:

```text
...?key=<api_key>
```

Query parameters can appear in:

- proxy logs;
- network traces;
- debugging output;
- telemetry;
- browser/dev tooling.

This is less desirable than an HTTP header if the API supports it.

## Required action

Use the provider's recommended header/authentication mechanism where supported.

At minimum ensure the URL is never logged.

---

# 65. P1 — [HELP WANTED] Provider Error Handling Collapses Important Failure Classes

## Files

- Google provider;
- Anthropic provider;
- local provider;
- registry.

## Problem

Many exceptions become generic:

```text
RuntimeError("Provider chat failed...")
```

The UI cannot distinguish:

```text
invalid key
rate limit
network
timeout
model retired
content blocked
server error
```

## Required fix

Introduce typed provider errors:

```text
AuthenticationError
RateLimitError
NetworkError
TimeoutError
ModelNotFoundError
ProviderUnavailableError
ContentPolicyError
```

Map them to safe UI messages.

---

# 66. P2 — [HELP WANTED] Provider Streaming JSON Parse Errors Are Silently Ignored

## File

`core/providers/google.py`

## Problem

The code contains:

```python
except (ImportError, Exception):
    continue
```

This catches everything and discards it.

That can silently drop chunks and return incomplete output.

## Required fix

Catch only expected JSON/SSE parse errors.

Track malformed event count.

If the stream becomes invalid, fail the stream rather than silently producing truncated output.

---

# 67. P2 — [HELP WANTED] Anthropic Streaming Also Ignores Some Parse Errors

## File

`core/providers/anthropic.py`

## Required action

Do not silently discard all malformed SSE events.

Differentiate:

```text
keepalive
unknown event
malformed event
provider error
```

---

# 68. P1 — [HELP WANTED] Cloud Model Capability Metadata Can Be Wrong

## Files

- Google provider;
- Anthropic provider.

## Problem

Hardcoded metadata claims tools/vision/JSON support for models.

Capability mismatches can cause the UI/router to choose unsupported features.

## Required fix

Validate capabilities from live metadata where available.

If using static fallback metadata, mark it as approximate and validate at request time.

---

# 69. P2 — [HELP WANTED] Local Model Chat Template Is Hardcoded to Gemma

## File

`core/providers/local.py`

## Problem

`format_gemma_prompt()` is always used.

If the downloaded DBERT model is not actually a Gemma-compatible chat model, prompts can be malformed.

## Required fix

Obtain the chat template from model metadata/manifest where available.

Do not infer model family solely from filename.

---

# 70. P1 — [HELP WANTED] Model Downloaded From Ollama May Have a System Template That Is Ignored

## File

`core/model_fetch/ollama_pull.py`

## Problem

The downloader saves:

```text
chat_template.txt
```

but the local provider still uses its own hardcoded Gemma template.

The downloaded template therefore appears unused.

## Required fix

Either:

- load and use the downloaded template;
- or remove the unused template download.

This is a concrete dead-end.

---

# 71. P2 — [HELP WANTED] Downloaded Params Metadata Is Not Clearly Used

## File

`core/model_fetch/ollama_pull.py`

## Problem

The downloader saves:

```text
params.json
```

but local inference configuration appears driven by `core/config.py` and hardware detection.

## Required action

Either consume the params metadata or remove it from the pipeline.

---

# 72. P1 — [HELP WANTED] RAG Feature Claims Must Match Actual Implementation

## Files

- `README.md`
- `core/config.py`
- optional dependencies
- project tree.

## Problem

The project architecture references document/RAG functionality, but the current tree should be checked for actual retrieval/indexing implementation.

Do not advertise RAG if the runtime cannot actually:

```text
ingest
chunk
embed
retrieve
inject
```

documents.

## Required action

Either implement the feature or explicitly mark it experimental/not available.

---

# 73. P1 — [HELP WANTED] Training Pipeline Is Not Reproducible Enough

## Files

- `training/generate_data.py`
- `training/colab_notebook.py`

## Required action

Audit:

- random seeds;
- dataset version;
- model base version;
- tokenizer;
- training parameters;
- output artifact identity;
- dependency versions.

The final GGUF should have traceable metadata back to:

```text
dataset
commit
training config
base model
conversion parameters
```

---

# 74. P2 — [HELP WANTED] Training Data Generation Needs Validation Against Duplicates

If generated training examples contain duplicate/near-duplicate prompts, the fine-tuned model may overfit to templates.

Add:

- exact duplicate detection;
- normalized duplicate detection;
- train/evaluation split checks.

---

# 75. P1 — [HELP WANTED] Educational Safety: Specialized Agents Are Not Actually Grounded

Many prompt agents claim specialized expertise:

```text
Financial Agent
Legal Review Agent
Clinical Analysis Agent
HR Agent
etc.
```

but they primarily call the same local model with a system prompt.

This is not inherently a bug, but the UI/README must not imply validated domain expertise.

## Required action

Use clear labels:

```text
AI-assisted draft
not professional advice
verify important claims
```

for high-stakes domains.

---

# 76. P1 — [HELP WANTED] Legal/Medical/Financial Agents Need Stronger Safety Routing

If the app is intended for general students, specialized agents can generate high-stakes advice.

At minimum:

- add domain safety prompts;
- uncertainty handling;
- no fabricated credentials;
- encourage professional verification;
- avoid presenting guesses as facts.

Add regression tests for dangerous overconfidence.

---

# 77. P1 — [HELP WANTED] Prompt Injection From User Content Can Override Agent Instructions

The application is an agentic system.

User content can contain:

```text
Ignore your system prompt.
Call tool X.
Reveal API key.
```

Even without external tools, malicious instructions can alter model behavior.

## Required fix

Clearly delimit untrusted user content in prompts.

For tool-enabled paths:

```text
system instructions
tool policy
untrusted user content
```

Do not treat user text as system-level instructions.

---

# 78. P1 — [HELP WANTED] Tool Results Are Also Untrusted Content

A tool may return web/document/user-controlled text containing prompt injection.

The runtime currently feeds tool results directly back into the agent context.

## Required fix

Label tool output as untrusted data.

Add tool-output size limits.

Add prompt-injection tests.

---

# 79. P1 — [HELP WANTED] Tool Arguments Need Size and Resource Limits

A model can request:

```text
huge string
huge list
path traversal
unexpected file
```

depending on available tools.

Validate and cap all arguments before execution.

---

# 80. P1 — [HELP WANTED] Local File/Document Features Need Path Traversal Review

Audit all document/file-related tools and UI bridge slots.

Reject:

```text
..\..\secret
absolute system paths
UNC paths
symlink escapes
```

when the feature is supposed to operate inside a controlled workspace.

---

# 81. P1 — [HELP WANTED] QWebChannel Bridge Is a Privileged Boundary

## File

`app/bridge.py`

JavaScript can invoke Python slots.

Treat every exposed slot as privileged.

Audit all `@Slot` methods for:

- path input;
- settings input;
- provider keys;
- model operations;
- filesystem operations;
- session IDs.

Validate all inputs.

Do not assume that because the HTML is local it is inherently trustworthy.

---

# 82. P2 — [HELP WANTED] Bridge Methods Return Inconsistent Error Shapes

Examples include:

```text
[]
{"ok": false}
{"installed": false}
plain error string
```

## Required fix

Define consistent response schemas.

Example:

```json
{
  "ok": false,
  "error": {
    "code": "MODEL_UNAVAILABLE",
    "message": "..."
  }
}
```

---

# 83. P2 — [HELP WANTED] Silent Empty List Fallbacks Hide Provider/Session Errors

Examples:

```python
return json.dumps([])
```

on errors.

This can be indistinguishable from:

```text
no providers
no models
no sessions
```

## Required fix

Return explicit error status.

---

# 84. P1 — [HELP WANTED] Model Download and Provider Operations Need Timeouts Exposed as Config

Avoid scattering magic timeouts:

```text
10s
15s
30s
120s
300s
```

Centralize timeout policy.

---

# 85. P2 — [HELP WANTED] HTTP Client Usage Is Recreated Repeatedly

Providers use top-level convenience methods:

```python
httpx.get()
httpx.post()
httpx.stream()
```

This prevents connection pooling and consistent configuration.

## Required improvement

Use a reusable `httpx.Client` where appropriate.

Ensure it is closed correctly.

---

# 86. P2 — [HELP WANTED] No Offline Mode Contract for Cloud-Enabled Components

The application is described as local-first.

Define:

```text
offline mode
```

where all network calls are disabled.

This is useful for both privacy and testing.

---

# 87. P1 — [HELP WANTED] No Network Egress Audit Test

Add a test that monkeypatches HTTP/network functions and verifies:

```text
LOCAL_ONLY
```

does not make external requests.

---

# 88. P1 — [HELP WANTED] No Model Context Overflow Guard

Before sending a prompt:

```text
system + history + user + expected output
```

must fit within model context.

## Required behavior

If too large:

1. trim history;
2. optionally summarize history;
3. preserve current turn;
4. never silently truncate the user's current input.

---

# 89. P2 — [HELP WANTED] No Maximum Input Size

Very large user messages can:

- consume model context;
- cause UI lag;
- cause high CPU/RAM usage;
- create pathological prompt processing.

Add configurable maximum input size with a user-friendly message.

---

# 90. P1 — [HELP WANTED] Streaming Backpressure / UI Performance

Every generated chunk immediately emits a Qt signal.

Long streams can generate hundreds/thousands of UI updates.

## Required improvement

Batch tokens periodically, e.g.:

```text
20–50 ms
```

or a reasonable chunk threshold.

Do not block the UI thread.

---

# 91. P2 — [HELP WANTED] Conversation UI Does Not Clearly Show Agent/Model Used

The backend tracks agent/model metadata, but the streaming UI should expose enough information for users to understand which agent handled the request.

Avoid misleading "Local Mode" labels when a cloud provider is used.

---

# 92. P1 — [HELP WANTED] "Local Mode" UI Label Can Be Misleading

## File

`app/ui/index.html`

The title says:

```text
Gayatri AI — Local Mode
```

even though the project has cloud provider infrastructure.

If cloud routing becomes active, this is misleading.

## Fix

Make the title/status dynamic:

```text
Local
Cloud: Anthropic
Cloud: Google
```

---

# 93. P2 — [HELP WANTED] UI Does Not Expose Privacy State

If PII redaction or cloud routing is active, the user should know.

Add a privacy indicator:

```text
Local only
PII redaction ON
Cloud provider active
```

without exposing the PII itself.

---

# 94. P1 — [HELP WANTED] PII Redaction Only Covers a Small Set of PII

Current regexes cover common:

- email;
- Indian phone;
- US phone;
- SSN-like;
- credit-card patterns.

They do not reliably detect:

- names;
- addresses;
- Aadhaar;
- PAN;
- student IDs;
- school IDs;
- dates of birth;
- account numbers;
- API tokens;
- passwords;
- authentication headers.

## Required action

Do not advertise the redactor as comprehensive PII protection.

Either expand detection or clearly label it:

```text
basic pattern-based PII filtering
```

---

# 95. P1 — [HELP WANTED] PII Regexes Can Produce False Positives

Phone/card patterns can match legitimate:

- IDs;
- mathematical numbers;
- code;
- dates.

## Required fix

Use contextual validation and preserve false-positive-safe behavior.

Tests should include ordinary educational content containing long numbers.

---

# 96. P2 — [HELP WANTED] PII Redaction Result Stores Original PII In Memory

`RedactionResult.redactions` contains the original values.

This is necessary for restoration, but the lifetime should be minimized.

Do not persist `RedactionResult`.

Do not log original values.

Document memory handling.

---

# 97. P2 — [HELP WANTED] PII Logging Summary Is Safe but Must Remain Type-Only

Keep logs like:

```text
2 EMAIL
1 PHONE_IN
```

Do not add original values during debugging.

Add a regression test that logging does not contain input PII.

---

# 98. P1 — [HELP WANTED] Error Recovery Must Not Accidentally Re-send Unredacted Input

Audit every retry path.

Required invariant:

```text
user input
  ↓
redaction
  ↓
all providers/retries/tools
```

No retry may bypass redaction.

---

# 99. P1 — [HELP WANTED] PII Redaction and Session Persistence Must Share the Same Policy

The current orchestrator redacts before adding user messages to conversation, which is good.

Verify all alternative entry points also do this:

- submit;
- stream;
- direct agent calls;
- tests;
- future bridge methods.

Add one central input-normalization function if needed.

---

# 100. P2 — [HELP WANTED] `Conversation` Claims Thread Safety but Higher-Level State Is Not Thread-Safe

`Conversation` itself uses a lock.

But:

- TutorEngine session dictionary;
- AgentRuntime state;
- Provider singleton;
- bridge state

may not.

Document the actual concurrency guarantee.

---

# 101. P1 — [HELP WANTED] `AgentRuntime._step_count` Should Not Be Shared Mutable State

The current `_agent_loop()` uses a local `step_count`, which is better than the historical shared counter.

Keep it local.

Do not reintroduce instance-level mutable counters.

Add a concurrency regression test.

---

# 102. P2 — [HELP WANTED] Agent Runtime Does Not Enforce Agent Tool Allow-List

`AgentSpec` has:

```python
tools
```

but the runtime should verify that every requested tool belongs to the agent's allowed tools.

## Required invariant

An agent may only call tools declared by its `AgentSpec`.

---

# 103. P1 — [HELP WANTED] Agent Tool Call Can Be Forged by Model Output

Tool calls are represented as dictionaries.

Validate:

```text
tool name
arguments
agent permission
schema
```

before execution.

---

# 104. P2 — [HELP WANTED] Agent Registry Duplicate Names Need Explicit Handling

`register()` should not silently overwrite an existing agent with the same name.

Raise or warn clearly.

---

# 105. P2 — [HELP WANTED] Prompt-Agent Registration Is Global and Import-Order Sensitive

`register_prompt_agents()` checks for one specific agent name.

If partial registration occurs before an exception, the next call may skip or duplicate registration depending on state.

Make registration atomic or track a registration version.

---

# 106. P2 — [HELP WANTED] Default Agent Registration Should Be Idempotent and Testable

Add tests:

```text
register once
register twice
registry contents unchanged
```

---

# 107. P1 — [HELP WANTED] `get_next_concept()` Can Return None Without Explaining Why

The tutor can reach:

```text
No concepts unlocked
```

or an empty curriculum.

The user may receive generic model output rather than a meaningful curriculum status.

## Required fix

Expose:

```text
CURRICULUM_EMPTY
NO_CONCEPT_AVAILABLE
PREREQUISITES_BLOCKED
```

to the tutor layer.

---

# 108. P2 — [HELP WANTED] LDG Selection Tie-Breaking Does Not Match Its Documentation

The documentation says:

```text
least recently practiced
```

but the actual sort uses:

```python
-(c.exposure_count)
```

which prefers low exposure, not necessarily least recent practice.

## Required fix

Use `last_practiced` if that is the intended criterion.

Add tests.

---

# 109. P1 — [HELP WANTED] LDG `get_mastery()` Treats Missing Concepts as Zero

## File

`core/knowledge_graph.py`

```python
return concept.mastery if concept else 0.0
```

This conflates:

```text
concept mastery = 0
```

with:

```text
concept does not exist
```

## Impact

A missing prerequisite can appear completely unmastered rather than invalid.

## Required fix

Raise/return explicit missing state for invalid concept IDs.

---

# 110. P1 — [HELP WANTED] Missing Prerequisite Data Can Produce Permanent Curriculum Deadlocks

If an edge references a deleted/missing concept, the current logic can keep a concept locked forever.

Add graph integrity validation.

---

# 111. P2 — [HELP WANTED] Database Connections Should Have Explicit Transaction/Error Handling

Audit:

- `core/db.py`
- `core/session.py`
- `core/knowledge_graph.py`

for:

- connection leaks;
- commits after partial writes;
- rollback on exceptions;
- foreign-key enforcement;
- migrations.

Add integration tests that intentionally fail mid-transaction.

---

# 112. P1 — [HELP WANTED] SQLite Schema Migration Strategy Must Be Explicit

If the application updates from one version to another, existing databases need migration.

Do not assume:

```text
CREATE TABLE IF NOT EXISTS
```

is sufficient for schema evolution.

Add:

```text
schema_version
migration steps
backup before migration
```

---

# 113. P2 — [HELP WANTED] SQLite Concurrent Access Needs WAL/Busy Timeout Review

Desktop threads may access SQLite concurrently.

Configure:

```text
WAL
busy_timeout
foreign_keys=ON
```

where appropriate.

Test concurrent session/tutor updates.

---

# 114. P2 — [HELP WANTED] Database Location Must Be User-Data Location

Verify that the application does not write mutable databases inside the source/repository directory.

Use OS-appropriate application-data directories.

---

# 115. P2 — [HELP WANTED] Generated Model/Data Files Must Not Be Accidentally Committed

Audit `.gitignore` for:

```text
models/
*.gguf
settings.json
secrets.enc
*.db
*.sqlite
logs/
__pycache__/
```

Do not ignore source fixtures that are intentionally part of the project.

---

# 116. P1 — [HELP WANTED] README Setup Must Match Actual Python Version and Dependencies

The current project metadata specifies:

```text
Python >=3.12,<3.13
```

The setup documentation must be checked for consistency.

Do not tell users to use a different Python version.

---

# 117. P1 — [HELP WANTED] `requirements.txt` and `pyproject.toml` Must Have a Single Source of Truth

Currently both exist.

They can drift.

## Required action

Either:

- generate requirements from pyproject;
- or document exactly why both exist and keep them synchronized.

CI should test installation from both paths.

---

# 118. P1 — [HELP WANTED] `setup.bat` and `launch.bat` Must Be Tested on a Clean Windows Environment

The project is explicitly Windows-oriented.

Test:

```text
fresh checkout
Python 3.12
setup.bat
launch.bat
```

Verify:

- venv creation;
- dependency installation;
- model detection;
- app launch;
- failure messages.

---

# 119. P2 — [HELP WANTED] Batch Scripts Need Quoting and PATH Robustness

Audit spaces in installation paths.

Use:

```bat
"%PYTHON%"
"%VENV%\Scripts\python.exe"
```

rather than relying on current directory or PATH.

---

# 120. P1 — [HELP WANTED] Installation Must Fail Clearly When `llama-cpp-python` Cannot Be Installed

`llama-cpp-python` can be platform/build-sensitive.

The setup process should distinguish:

```text
package install failed
model missing
model invalid
runtime load failed
```

rather than leaving the user at a generic failure.

---

# 121. P2 — [HELP WANTED] Optional CUDA Dependency Needs Platform Compatibility Checks

The `[cuda]` extra should not claim universal compatibility.

Document supported CUDA/Python/platform combinations.

---

# 122. P1 — [HELP WANTED] No CI Pipeline Is Visible

The repository's quality stack mentions:

```text
pytest
pytest-qt
ruff
```

but the GitHub repository should be checked for automated CI.

If no CI exists, add a minimal workflow for:

```text
Python 3.12
pip install -e .[dev]
pytest
ruff check
```

Avoid trying to load a huge GGUF model in CI.

---

# 123. P2 — [HELP WANTED] Tests Are Too Narrow

Current tests are concentrated around:

- agent registry;
- DB;
- session;
- a few regression checks.

Add tests for:

```text
privacy
tutor engine
knowledge graph
model fetch
providers
settings
orchestrator
bridge contracts
UI JS invariants
```

where practical.

---

# 124. P1 — [HELP WANTED] Existing Regression Test for Bug #1 Is a No-Op

## File

`tests/test_regressions.py`

The test:

```python
def test_regression_bug_1_model_progress_args():
    ...
    pass
```

does not test anything.

## Required fix

Replace it with an actual test.

Possible strategy:

- monkeypatch `_download_blob`;
- invoke `pull_model()`;
- have fake downloader invoke callback with three arguments;
- verify no `TypeError`.

---

# 125. P2 — [HELP WANTED] Tests Use Source-Text Assertions Instead of Behavioral Tests

Examples:

```python
assert "LDG_MASTERY_THRESHOLD" in content
assert "addMessage('assistant', '');" in content
```

These can pass even when behavior is broken.

## Required improvement

Prefer behavioral tests.

Source inspection tests should be used only when a true runtime test is impractical.

---

# 126. P2 — [HELP WANTED] Missing Integration Tests Across Orchestrator → Agent → Tutor → Persistence

This is the highest-value integration path.

Create at least one end-to-end test:

```text
user question
↓
agent dispatch
↓
tutor context
↓
model response mocked
↓
student answer
↓
assessment
↓
mastery update
↓
session persistence
↓
reload
```

---

# 127. P1 — [HELP WANTED] Tutor Agent Prompt Says "Never Give Direct Answers"

This can be pedagogically counterproductive.

A student may explicitly request:

```text
show me the solution
```

The tutor is forced to never give direct answers.

## Required action

Define controlled escalation:

```text
hint 1
hint 2
worked example
full explanation
```

based on student struggle.

This is a product/education logic issue, not just a prompt wording issue.

---

# 128. P2 — [HELP WANTED] Tutor Waiting State Can Become Stale

If a student changes topic while `waiting_for_answer=True`, the next unrelated message may be treated as the answer to the previous question.

## Required fix

Detect topic changes or explicit commands and reset waiting state.

Tests:

```text
question
↓
student asks unrelated question
↓
should not mark old answer correct/incorrect
```

---

# 129. P1 — [HELP WANTED] Tutor Evaluation Runs Before Routing Context Is Fully Established

Current orchestration calls:

```text
_evaluate_tutor_response()
_inject_tutor_context()
```

when the selected agent is Tutor.

This is correct in ordering for feedback, but the agent-routing decision itself determines whether the student's response is assessed.

If a student answers a tutor question with wording that routes to another agent, the tutor state may never be evaluated.

## Required fix

Tutor waiting-state detection should be evaluated before general agent routing when the session is explicitly waiting for a tutor answer.

---

# 130. P1 — [HELP WANTED] Tutor State Can Be Updated Even If the Model Response Failed

Audit the order:

```text
evaluate previous answer
generate response
post waiting state
```

If generation fails, the system should not necessarily mark the tutor as having successfully asked a new question.

## Required invariant

Only enter:

```text
waiting_for_answer=True
```

if the tutor response actually contains a question requiring an answer.

---

# 131. P2 — [HELP WANTED] Tutor `last_response_type` Semantics Are Ambiguous

The code uses:

```text
explain
question
practice
feedback
```

but transitions should be formally defined.

Add state-transition tests.

---

# 132. P1 — [HELP WANTED] Session IDs Must Be Validated at Persistence Boundaries

Session IDs are generated as UUIDs, but APIs/load functions accept arbitrary strings.

Ensure:

- reasonable length;
- allowed characters;
- no path semantics;
- no SQL injection risk;
- no cross-session overwrite.

Parameterized SQL already helps, but validation remains useful.

---

# 133. P1 — [HELP WANTED] Session Loading Must Not Load Arbitrary User-Controlled Database Rows Into Another Session

Audit `load_session()` and bridge session-switching logic.

Verify:

```text
selected session ID
↓
only that session's messages
↓
active conversation replaced safely
```

---

# 134. P2 — [HELP WANTED] Session Switching While Generation Is Active Is Unsafe

The UI/bridge should prevent:

```text
generation running
↓
new chat/session selected
↓
old generation finishes
↓
writes response into wrong active session
```

Add a session-generation binding.

Every generation should carry the session ID it started with.

---

# 135. P1 — [HELP WANTED] New Chat During Active Generation Needs a Guard

Same race as above.

Either:

- disable New Chat;
- cancel generation;
- or let generation finish against the original session.

---

# 136. P2 — [HELP WANTED] Application Close During Generation Needs Cancellation

A running local model generation should not be allowed to keep mutating objects after the window is destroyed.

Define shutdown/cancellation semantics.

---

# 137. P1 — [HELP WANTED] Cloud Provider Requests Must Respect Offline Mode

No cloud provider should be instantiated/called when privacy/offline mode is active.

Add network-block tests.

---

# 138. P2 — [HELP WANTED] Model Router Should Not Treat Cost/Speed Metadata as Authoritative

Static cost values can become stale.

If displayed, label as estimates.

---

# 139. P1 — [HELP WANTED] Model Catalog Should Not Present Retired Models as User-Selectable

Before selection, verify model availability.

If unavailable:

```text
disabled + reason
```

rather than allowing a guaranteed failure.

---

# 140. P2 — [HELP WANTED] API/Provider Errors Need Correlation IDs

For support/debugging, generate a short diagnostic ID:

```text
ERR-2026-XXXX
```

and log full details locally.

Do not expose secrets.

---

# 141. P2 — [HELP WANTED] Logging Configuration Must Be Audited for PII/Secrets

Search for logs containing:

```text
user_message
api_key
Authorization
tool arguments
provider response
PII originals
```

Do not log sensitive content by default.

---

# 142. P1 — [HELP WANTED] Cloud Responses Can Contain Sensitive Data and Must Not Be Logged Wholesale

Provider debug logging should never dump complete responses by default.

---

# 143. P2 — [HELP WANTED] Error Strings From Providers Should Be Sanitized Before Logging/UI

Some SDK/API errors may echo request content.

Use safe error wrappers.

---

# 144. P1 — [HELP WANTED] "Privacy First" Claims Need a Threat Model

Add a `SECURITY.md` or privacy section documenting:

- what stays local;
- what can leave the device;
- what is redacted;
- limitations of regex PII detection;
- where API keys are stored;
- what telemetry exists;
- what logs contain;
- Windows-only guarantees;
- non-Windows limitations.

---

# 145. P2 — [HELP WANTED] README Claims Need Verification Against Runtime

Audit every major README claim:

- local-first;
- privacy-first;
- agent orchestration;
- fine-tuned local model;
- learning dependency graph;
- cloud APIs;
- document/RAG support;
- model download;
- training pipeline;
- Windows setup.

Every claim should correspond to a working path or be labeled experimental.

---

# 146. P1 — [HELP WANTED] The Existing `BUGS.md` Should Become a Living Engineering Checklist

After fixing issues, update `BUGS.md` or replace it with a status-based audit:

```text
[FIXED]
[VERIFIED]
[CONDITIONAL]
[KNOWN LIMITATION]
[NOT IMPLEMENTED]
```

Do not leave fixed bugs listed as if they remain unresolved.

---

# 147. Conditional Failure Matrix

The local agent must explicitly test these conditions.

| Condition | Expected result |
|---|---|
| Model file missing | Clear model-unavailable state |
| Model file partial | Not installed |
| Model digest mismatch | Download rejected |
| Model server unavailable | Clear network error |
| Cloud API key invalid | Authentication error |
| Cloud API rate limited | Rate-limit state |
| Cloud API offline | Provider unavailable |
| No agent match | Safe general response |
| Ambiguous agent match | General/fallback agent |
| Tutor answer uncertain | No mastery increase |
| Tutor curriculum empty | Explicit curriculum state |
| Tutor prerequisite missing | Explicit blocked state |
| DB unavailable | Persistence error, not fake success |
| Session load fails | Explicit recovery state |
| UI bridge unavailable | Disabled UI / visible status |
| Concurrent generation | Rejected or queued safely |
| App closes during generation | Safe cancellation |
| Download cancelled | Partial file not considered installed |
| Disk space insufficient | Preflight failure |
| Corrupt secrets vault | Explicit corruption status |
| Non-Windows secret storage | Secure store or explicit insecure opt-in |
| Cloud provider model retired | Model unavailable |
| Provider catalog fetch fails | Offline catalog, not "available" |
| Stream malformed | Explicit stream failure |
| Tool missing | Tool error, no infinite retry |
| Tool timeout | Bounded failure |
| Tool unauthorized | Block execution |
| Prompt injection | Treat as untrusted content |

---

# 148. Required Regression Test Suite

Add tests for at least:

## Privacy

- multiple PII values;
- placeholder collision;
- model-generated placeholder;
- mixed PII;
- restore correctness;
- no original PII in logs.

## Tutor

- correct answer;
- incorrect answer;
- uncertain answer;
- long incorrect answer;
- short correct answer;
- topic switch while waiting;
- session reload;
- mastery threshold;
- prerequisite blocking.

## Agents

- exact command;
- phrase trigger;
- ambiguous trigger;
- single-word trigger;
- tie;
- duplicate registration;
- unauthorized tool call.

## Runtime

- tool timeout;
- tool failure;
- tool loop limit;
- error sanitization;
- no duplicate terminal events.

## Providers

- invalid key;
- unavailable provider;
- stale model;
- fallback catalog;
- tool support;
- JSON mode;
- stream parse failure.

## Model download

- progress callback;
- resume;
- invalid content-range;
- cancellation;
- digest mismatch;
- insufficient disk;
- partial-file status.

## Persistence

- save/load;
- crash-safe transaction;
- schema migration;
- concurrent access;
- session switching.

## UI/bridge

- bridge not ready;
- send during generation;
- new chat during generation;
- close during download;
- error response;
- dynamic model status.

---

# 149. Static Analysis / Quality Gates

Run:

```bash
pytest -q
ruff check .
ruff format --check .
```

Also run:

```bash
python -m compileall app core tests
```

Run packaging validation:

```bash
python -m pip install -e .[dev]
```

in a clean Python 3.12 environment.

If Windows is available:

```bat
setup.bat
launch.bat
```

must be tested.

---

# 150. Security Checks

Before opening the PR:

- search for API keys;
- search for passwords;
- search for tokens;
- inspect `.env` references;
- inspect secrets/logging;
- inspect model download URLs;
- inspect path-handling code;
- inspect subprocess usage;
- inspect QWebChannel slots;
- inspect tool execution;
- inspect cloud-provider authentication.

No secrets may appear in the branch.

---

# 151. Repository Hygiene

Ensure the PR does not add:

```text
*.gguf
*.db
*.sqlite
*.log
__pycache__/
*.pyc
secrets.enc
settings.json
temporary model files
download fragments
```

unless explicitly intended as test fixtures.

---

# 152. Recommended Implementation Order

## Phase 1 — Correctness/Safety

1. Tutor assessment safety.
2. PII restore integrity.
3. PII placeholder injection protection.
4. secrets fallback/security.
5. provider capability correctness.
6. model download installation-state correctness.
7. session/tutor-state consistency.
8. stream error handling.

## Phase 2 — Runtime Reliability

9. tool permissions/schema/timeout.
10. provider error taxonomy.
11. model context limits.
12. concurrency/session-generation binding.
13. download cancellation/cleanup.
14. provider availability semantics.

## Phase 3 — UX

15. functional sidebar tabs.
16. model status correctness.
17. dynamic local/cloud/privacy status.
18. retry/error states.
19. agent selector behavior.

## Phase 4 — Persistence

20. SQLite transaction/migration review.
21. tutor state persistence.
22. autosave policy.
23. session switching.

## Phase 5 — Quality

24. regression tests.
25. integration tests.
26. CI.
27. README/security documentation.
28. clean old `BUGS.md`.

---

# 153. Agent Rules

The local coding agent must:

1. Work on a new branch.
2. Never directly modify `main`.
3. Verify the current code before applying a finding.
4. Prefer minimal, targeted fixes.
5. Avoid unrelated refactors.
6. Do not remove functionality just to make tests pass.
7. Do not weaken privacy/security protections.
8. Do not turn uncertain educational assessment into false certainty.
9. Do not expose API keys or secrets in logs/tests.
10. Do not add fake tests that only inspect source strings when behavioral tests are possible.
11. Do not silently suppress exceptions merely to keep the application running.
12. Do not claim a feature is fixed without a regression test where practical.
13. Preserve backwards compatibility unless a breaking change is justified.
14. Update documentation for every changed public behavior.

---

# 154. Pull Request Requirements

## Suggested branch

```text
fix/tutor-v3-comprehensive-audit
```

## Suggested PR title

```text
Fix Tutor V3 correctness, privacy, runtime, and reliability issues
```

## PR must contain

### Summary

Explain the main classes of defects fixed.

### Critical fixes

List P0 fixes.

### Reliability fixes

List P1/P2 fixes.

### Tests

Include exact commands and results.

Example:

```text
pytest -q
ruff check .
ruff format --check .
python -m compileall app core tests
python -m pip install -e .[dev]
```

### Security

Explain:

- PII handling;
- secret storage;
- cloud/local routing;
- tool restrictions;
- QWebChannel validation.

### Known limitations

Be explicit.

### Breaking changes

State API/configuration changes.

---

# 155. Acceptance Criteria

The task is complete only when:

- [ ] All P0 issues are fixed.
- [ ] P0 regression tests exist.
- [ ] Tutor uncertain answers cannot increase mastery.
- [ ] PII restoration is one-to-one and collision-safe.
- [ ] Model-generated placeholder text cannot trigger PII restoration.
- [ ] Secret storage fails safely outside Windows.
- [ ] Corrupt vault entries are observable.
- [ ] Provider availability is not confused with fallback model metadata.
- [ ] Unsupported provider capabilities are not advertised.
- [ ] Downloaded model identity is verified and persisted.
- [ ] Partial/cancelled model files are not reported as installed.
- [ ] Tutor state survives application restart or is deterministically reconstructed.
- [ ] Session switching cannot cross-contaminate generations.
- [ ] Tool execution is permission- and schema-validated.
- [ ] Tool execution has bounded runtime.
- [ ] Streaming emits exactly one terminal event.
- [ ] Infrastructure errors are not persisted as assistant messages.
- [ ] UI critical initialization errors are not silently swallowed.
- [ ] Sidebar controls are functional or removed.
- [ ] Model/provider/privacy status is accurate.
- [ ] Cloud/local behavior is explicit.
- [ ] Input/context limits are enforced.
- [ ] SQLite behavior is transactional and migration-safe.
- [ ] Tests cover the critical paths.
- [ ] CI/static checks pass.
- [ ] Documentation matches actual implementation.
- [ ] No secrets or generated artifacts are introduced.
- [ ] PR is opened against `main`.

---

# 156. Final Agent Report

The PR description must finish with:

```text
Repository:
Branch:
PR:

Baseline:
Final:

P0 fixed:
- ...

P1 fixed:
- ...

P2 fixed:
- ...

Regression tests:
- ...

Integration tests:
- ...

Security checks:
- ...

Documentation:
- ...

Known remaining limitations:
- ...

Not fixed intentionally:
- ...
```

The agent must distinguish between:

```text
FIXED
VERIFIED
CONDITIONAL
KNOWN LIMITATION
NOT IMPLEMENTED
```

and must not mark an issue "fixed" merely because the application starts.
