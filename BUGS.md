# Gayatri Tutor V3 — Bug Report

Reviewed: `github.com/Gayatri-Education/Gayatri-Tutor-V3` (branch `main`, commit at time of review)
Scope: everything under `app/` and `core/` (bridge, orchestrator, agents, providers, privacy, security, config, hardware, DB, frontend HTML/JS) plus `pyproject.toml` / `requirements.txt`.

Fix these locally, verify, then push. Ordered by severity.

---

## 🔴 Critical — will crash / silently break a core feature every time it runs

### 1. Model download always crashes on first progress update
**File:** `core/model_fetch/ollama_pull.py` — `pull_model()`, lines ~258–262

```python
def _model_progress(downloaded: int, total: int):      # only 2 params
    if progress_callback:
        progress_callback("model", downloaded, total)

_download_blob(model_url, model_path, model_digest, _model_progress)
```

`_download_blob()` invokes the callback as `progress_callback("model", downloaded, total)` — **3 positional args** — but `_model_progress` only accepts 2 (`downloaded`, `total`). The very first chunk written during a model download raises:

```
TypeError: _model_progress() takes 2 positional arguments but 3 were given
```

This breaks **every** model download, whether triggered from `app/bridge.py::download_model()` or `app/install_hook.py`. This is likely the #1 reason "download model" fails/hangs for users.

**Fix:** give `_model_progress` a matching signature, e.g. `def _model_progress(label, downloaded, total):`.

---

### 2. Anthropic provider crashes on any tool-call response
**File:** `core/providers/anthropic.py` — `chat()`, line ~205

```python
"arguments": json.dumps(block.get("input", {})),
```

`json` is never imported in this file — not at module level, and not inside `chat()` (only `stream()` has a local `import json` at line 228). Any Claude response containing a `tool_use` block will raise `NameError: name 'json' is not defined`, crashing that provider call.

**Fix:** add `import json` at the top of `core/providers/anthropic.py`.

---

## 🟠 High — silent correctness / privacy bugs (no crash, wrong behavior)

### 3. PII redaction corrupts text when the same PII type appears twice
**File:** `core/privacy.py` — `PIIRedactor.redact()`

```python
for pii_type, pattern in self.PATTERNS:
    for match in pattern.finditer(result_text):
        ...
        result_text = result_text[:start] + placeholder + result_text[end:]
        offset += len(original) - len(placeholder)   # computed but never used!
```

`pattern.finditer(result_text)` is evaluated once per pattern, so `start`/`end` for the **second and later** matches of the *same* PII type are positions in the **original** string, not the string after the first replacement (which has already shifted length). Once a message contains two emails, two phone numbers, etc., the second replacement lands at the wrong offset and mangles the text (wrong characters get replaced with `[EMAIL]` etc., or the placeholder ends up mid-word). The `offset` variable is clearly meant to correct for this and is dead code — the fix was started but never finished.

**Fix:** either build the result by walking non-overlapping matches with a running offset applied to `start`/`end`, or do a single `pattern.sub()` pass per type instead of manual slicing.

### 4. Streaming path skips PII redaction entirely
**File:** `core/orchestrator.py` — `Orchestrator.stream()`, lines ~326–337

`submit()` calls `_redact_pii(user_message)` before building the model prompt. `stream()` — the path actually used by the desktop UI via `app/bridge.py::send_message()` — never calls `_redact_pii()` at all:

```python
messages.append({"role": "user", "content": user_message})  # raw, unredacted
```

So the privacy module exists but the production chat path (streaming) never uses it. Additionally, even in `submit()`, only the *current* message is redacted — the conversation history re-sent every turn (`conv.get_recent(10)`) still contains the original, unredacted text, since redaction happens only at send time and isn't applied when messages are stored.

**Fix:** apply `_redact_pii()` in `stream()` too, and consider redacting before storing into `Conversation`/`SessionStore` rather than only at prompt-build time.

### 5. Local model never gets its stop token — can ramble into fake follow-up turns
**File:** `core/providers/local.py` — `chat()` / `chat_stream()` / `stream()`

`format_gemma_prompt()` builds prompts using Gemma's `<end_of_turn>` tokens, but `stream()` defaults `stop = kwargs.get("stop", [])` and nothing in `chat()`/`chat_stream()` ever passes `stop=["<end_of_turn>"]`. Without it, `llama-cpp-python` has no stop sequence and the model can keep generating past its answer, hallucinating additional `<start_of_turn>user...` turns into the visible response.

**Fix:** default `stop` to `["<end_of_turn>"]` in `chat`/`chat_stream` unless explicitly overridden.

### 6. Tutor "prerequisites not met" instruction is never sent to the model (key name mismatch)
**Files:** `core/orchestrator.py::_inject_tutor_context()` sets `tutor_meta["prerequisites_not_met"]`, but `core/agents/default_agents.py::_get_tutor_context()` reads:

```python
if tutor_meta.get('prerequisites_needed'):   # wrong key — always None
```

The keys don't match (`prerequisites_not_met` vs `prerequisites_needed`), so the "IMPORTANT: the student needs to master prerequisites first…" instruction is **dead code** — it can never fire, no matter what the LDG says.

**Fix:** rename one side to match the other (`prerequisites_not_met` everywhere is recommended, since that's what `orchestrator.py` and the LDG naturally track).

### 7. Tutor never gets told whether the student's last answer was right or wrong
**File:** `core/agents/default_agents.py::_get_tutor_context()`

```python
if tutor_meta.get('recent_attempt'):
    correct = tutor_meta['recent_attempt'].get('correct')
    ...
```

Nothing in `core/orchestrator.py::_inject_tutor_context()` ever sets a `"recent_attempt"` key on `tutor_meta` — the dict only contains `concept_id`, `concept_name`, `concept_description`, `mastery_pct`, `waiting_for_answer`, `prerequisites_not_met`, `prereq_names`. So the "praise them" / "gently correct them" branch is unreachable — the model is never explicitly told the last answer's correctness through this mechanism, even though `_evaluate_tutor_response()` in the orchestrator *does* compute and store it via `record_student_response()`. The plumbing between mastery-tracking and prompt-context is incomplete.

**Fix:** after `_evaluate_tutor_response()` scores the answer, stash the result (e.g., on `TutorContext`) and have `_inject_tutor_context()` include it as `tutor_meta["recent_attempt"] = {"correct": ...}`.

### 8. Chat UI overwrites the previous AI response instead of starting a new bubble
**File:** `app/ui/index.html` — `send()` / `updateLastMessage()`

```js
function send() {
  ...
  addMessage('user', msg);       // only a user bubble is added
  bridge.send_message(msg);
}

function updateLastMessage() {
  var msgs = chat.querySelectorAll('.message.assistant');
  var last = msgs[msgs.length - 1];   // grabs the PREVIOUS turn's bubble if one exists
  if (!last) { addMessage('assistant', ''); last = ...; }
  ...
}
```

`send()` never creates a placeholder assistant bubble for the new turn. On the first exchange this is masked because no `.message.assistant` exists yet, so `updateLastMessage()` creates one. From the **second** exchange onward, `querySelectorAll('.message.assistant')` finds the previous turn's bubble and streaming tokens overwrite it in place — the previous answer visually disappears and gets replaced by the new one instead of the conversation growing normally.

**Fix:** in `send()`, call `addMessage('assistant', '')` right after the user message (or track the "current" bubble via a variable set at the start of each turn) so `updateLastMessage()` always targets the newly-created one.

---

## 🟡 Medium

### 9. Streamed tokens are joined with an extra space, garbling output
**File:** `app/ui/index.html` — `updateLastMessage()`

```js
content.textContent = currentTokens.join(' ');
```

`chat_stream()`/`LocalProvider.stream()` yields raw text pieces exactly as produced by `llama-cpp-python` (sub-words, punctuation, etc.), which already contain any spacing they need. Joining them with an injected `' '` will produce output like `wonder ful` instead of `wonderful`, or `Hello , world` instead of `Hello, world`.

**Fix:** `currentTokens.join('')`.

### 10. Sidebar tabs (Agents / Courses / Settings) don't switch any content
**File:** `app/ui/index.html` — `switchTab(tab)`

```js
function switchTab(tab) {
  document.querySelectorAll('.sidebar-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
}
```

The `tab` parameter is accepted but unused — only the icon's `active` highlight changes. There is no corresponding panel markup or show/hide logic, so clicking "Agents", "Courses", or "Settings" only re-highlights the icon; the chat view never changes. Either the feature is unfinished or the panel-switching code was lost.

### 11. Invalid `pyproject.toml` build backend
**File:** `pyproject.toml`

```toml
[build-system]
build-backend = "setuptools.backends.legacy:build"
```

This is not a real setuptools entry point. The valid values are `setuptools.build_meta` (PEP 517, recommended) or `setuptools.build_meta:__legacy__`. As written, `pip install .` / `pip install -e .` / `python -m build` will fail to resolve the backend.

### 12. `pyproject.toml` optional dependencies key is misspelled
**File:** `pyproject.toml`

```toml
[project.optional-deps]
dev = [...]
rag = [...]
cuda = [...]
```

Per PEP 621 the key must be `[project.optional-dependencies]`. As written, `pip install .[dev]`, `.[rag]`, and `.[cuda]` will not install anything (the section is simply ignored by standards-compliant tooling), even though `development.md`/`setup.bat` likely assume these extras work.

### 13. Several dependencies are declared but never used; RAG has no implementation
**Files:** `requirements.txt`, `pyproject.toml`, `core/config.py`

`sqlite-vec`, `sentence-transformers`, `rank-bm25`, `pydantic`, `keyring`, and `cryptography` are all listed as dependencies, but a repo-wide search finds **zero imports** of any of them under `core/` or `app/`. `core/config.py` defines a full set of `RAG_*` constants (`RAG_CHUNK_SIZE`, `RAG_EMBEDDING_MODEL`, `RAG_DIR`, etc.) but there is no RAG module anywhere in the tree that uses them — the feature is configured but not implemented, and its dependencies are dead weight (and a large one: `sentence-transformers` pulls in torch).

Notably, `core/security/secrets.py` — which exists specifically to encrypt API keys — hand-rolls its own DPAPI wrapper via raw `ctypes` calls instead of using the `cryptography` or `keyring` packages that are already declared as dependencies for exactly that purpose.

### 14. Windows RAM detection can silently misreport on machines with >4GB RAM
**File:** `core/hardware.py` — `_get_ram_mb()`

```python
class MEMORYSTATUS(ctypes.Structure):
    _fields_ = [..., ("dwTotalPhys", ctypes.c_ulong), ...]
ctypes.windll.kernel32.GlobalMemoryStatus(ctypes.byref(mem))
```

`GlobalMemoryStatus` (no `Ex` suffix) is the legacy Win32 API, and its `dwTotalPhys` field is a 32-bit `DWORD` — it cannot represent RAM sizes above ~4GB and will wrap/cap. Since `recommend_llama_params()` uses this value to decide context size (`n_ctx`) and `use_mmap`, machines with 8/16/32GB of RAM can get under-provisioned inference settings.

**Fix:** use `GlobalMemoryStatusEx` with a `MEMORYSTATUSEX` struct (64-bit `ullTotalPhys`), remembering to set `dwLength` before the call.

### 15. Secrets vault only `chmod`s the file on the platform where `chmod` doesn't matter
**File:** `core/security/secrets.py` — `_save_vault()`

```python
if self._is_windows:
    try:
        os.chmod(self.vault_path, 0o600)
    except Exception:
        pass
```

POSIX file-permission bits are largely meaningless on Windows (DPAPI is already user-scoped there), while the actual insecure fallback path — non-Windows, base64 "encoding" explicitly commented as "NOT secure" — never restricts file permissions at all. The condition looks inverted from what would actually add defense-in-depth.

**Fix:** apply `os.chmod(..., 0o600)` on the non-Windows fallback path instead (or in addition).

### 16. Single-word fuzzy agent triggers cause aggressive misrouting
**File:** `core/agents/prompt_agents.py` (`register_prompt_agents`) + `core/agents/registry.py` (`AgentSpec.can_handle`)

The fuzzy-match scorer is `overlap / len(trigger_words)`. Several agents register **single-word** triggers, e.g.:

- Policy Analyst Agent: `"budget"`
- Crop Advisory Agent: `"weather"`
- Demand Forecasting Agent: `"seasonal"`
- Clinical Analysis Agent: `"trial"`
- Voice Assistant Agent: `"speak"`, `"listen"`

For a single-word trigger, any user message containing that one common word scores `1/1 = 1.0` confidence — the maximum possible — and will out-rank every other agent (`dispatch()` picks strictly-greater score). A message like "what's my budget for this month" or "will it rain, checking the weather" will get routed to Policy/Crop agents instead of a general response.

**Fix:** require multi-word trigger phrases (as most other agents already do), or set a minimum trigger length / weight single-word triggers lower.

---

## 🟢 Low — correctness edge cases, dead code, minor robustness

### 17. No cycle detection when adding prerequisite edges
**File:** `core/knowledge_graph.py` — `add_prerequisite()`

Only guards against a direct self-loop (`concept_id == prereq_id`). A longer cycle (A→B→C→A) is accepted silently. If it ever happens, `is_unlocked()` can never become true for the cycle members (deadlocked curriculum), and `get_learning_path()`'s Kahn's-algorithm sort will silently drop the cyclic concepts from its output rather than surfacing the problem.

### 18. Tutor mastery threshold lookup always uses a hardcoded fallback, ignoring config
**File:** `core/tutor_engine.py` — `get_next_concept_for_session()`

```python
if not current_id or self.ldg.get_mastery(current_id) >= self.ldg.__class__.__dict__.get("MASTERY_THRESHOLD", 0.85):
```

`LearningDependencyGraph` never defines a class attribute called `MASTERY_THRESHOLD` (the real constant is `LDG_MASTERY_THRESHOLD`, imported from `core/config.py` and used only inside `knowledge_graph.py`'s own methods). This lookup therefore always falls through to the literal `0.85` default. If `LDG_MASTERY_THRESHOLD` is ever tuned in config, this call site silently keeps using the old hardcoded value.

**Fix:** `from core.config import LDG_MASTERY_THRESHOLD` and compare against that directly.

### 19. Logged "previous mastery" value is inaccurate after clamping
**File:** `core/knowledge_graph.py` — `record_attempt()`

```python
logger.info(f"... mastery={concept.mastery:.3f} (was {concept.mastery - delta if correct else concept.mastery + delta:.3f})")
```

Mastery is clamped with `min(1.0, ...)` / `max(0.0, ...)` before this log line runs, so reconstructing "before" by adding/subtracting `delta` back out is wrong whenever clamping actually occurred (e.g., mastery was already near 1.0 or 0.0). Log-only issue, but makes the mastery-progression logs misleading during debugging.

### 20. `AgentRuntime` step counter is shared, mutable, and not thread-safe
**File:** `core/agents/runtime.py` — `AgentRuntime._step_count`

`Orchestrator` holds a single `AgentRuntime` instance shared across **all** sessions (`self.runtime = runtime or AgentRuntime(...)`), and `_step_count` is plain instance state reset at the top of `process()`. Combined with `app/bridge.py::send_message()` having no guard against concurrent calls (see #21), two turns processed concurrently (e.g., a fast double-submit, or multiple chat sessions) can race on the same counter, corrupting the tool-call step limit.

### 21. No guard against overlapping `send_message()` calls
**File:** `app/bridge.py` — `send_message()`

`self._generation_active` is set/read but never checked before starting a new generation — a second call while one is in flight will start a second concurrent `orch.stream()` for the same session, interleaving tokens from two turns into the UI and racing on the shared `Conversation` and `AgentRuntime` state described above.

**Fix:** early-return (or emit an error) if `self._generation_active` is already `True`.

### 22. Redundant duplicate agent dispatch every turn
**Files:** `core/orchestrator.py` (`submit`/`stream`) and `core/agents/runtime.py` (`AgentRuntime.process`)

`Orchestrator.submit()`/`stream()` already calls `self.registry.dispatch(user_message)` to get `spec`/`confidence` (used for `TurnResult.routing_reason` and to decide whether to inject tutor context), then calls `self.runtime.process(user_message, context)`, which calls `self.registry.dispatch(user_message)` **again** internally to pick the agent. Harmless today since dispatch is deterministic for the same input, but it's wasted work every turn and a footgun if dispatch logic ever becomes stateful/non-deterministic (e.g., after fixing #16).

### 23. Session title never updates after creation
**File:** `core/session.py` — `save_session()`

The `INSERT ... ON CONFLICT(id) DO UPDATE` clause only updates `updated_at` and `message_count`, not `title`. The title is fixed at whatever the *first* message's first 80 characters were at session creation — if that first message is empty or very short, the session keeps a near-blank title forever in the session list UI (`get_sessions()` in `app/bridge.py`).

### 24. Redundant exception handling
**File:** `core/hardware.py` — `_get_nvidia_gpu_info()`

```python
except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
```

Including `Exception` alongside more specific subclasses is redundant (it already catches everything) and is a sign this handler wasn't fully thought through — worth simplifying to just `except Exception:` for clarity, or narrowing intentionally if a specific exception should propagate.

---

## Suggested fix order

1. **#1 and #2** first — these are outright crashes on common user actions (downloading the model; using the Anthropic provider with tools).
2. **#3, #4, #6, #7** next — silent correctness/privacy bugs that undermine features the app advertises (PII redaction, LDG-aware tutoring).
3. **#5, #8, #9** — noticeably broken user-facing behavior (model rambling, chat bubbles overwriting each other, garbled streamed text).
4. **#11, #12, #13** — packaging fixes, cheap to do, unblock `pip install .[dev]` etc. for other contributors.
5. Remaining medium/low items as time allows; #16 (agent misrouting) is worth prioritizing before demoing the multi-agent feature.

Once these are fixed and verified locally (the repo's `tests/` directory covers only `agent_registry`, `db`, and `session` — consider adding regression tests for #1, #3, #6 and #8 since they have no test coverage today), push to `main`.
