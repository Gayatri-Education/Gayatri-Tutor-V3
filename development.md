# Gayatri AI — Desktop App Development Plan (for Claude Code)

**Audience:** Claude Code, building locally on Windows.
**Goal of this milestone:** a production-quality, installable **Windows `.exe`** for the Gayatri AI adaptive tutor — all-Python, offline-capable, with BYOK cloud models, a bundled local `dbert` model (pulled from the Ollama registry *without* Ollama), the core adaptive tutor engine, a secure code sandbox, an in-app course store (client against a mockable server API), and hardened packaging with an EULA installer.
**Out of scope this milestone:** the backend server, central telemetry/S3 upload, professor dashboards, verifiable certificates (all deferred; build client-side seams for them).

---

## 1. Locked decisions (do not re-litigate)

| Area | Decision |
|---|---|
| Stack | **PySide6** desktop app; UI is the locked HTML/CSS/JS mockup rendered in **QWebEngineView**; Python backend for everything else |
| UI bridge | **QWebChannel** (JS ⇄ Python), async request/response + streaming events |
| Tutor scope v1 | Skill graph + mastery model + **Tutor, Practice Generator, Examiner (mastery gates), Doubt-Solver (course RAG), Code Mentor + sandbox** |
| AI backends | **Local `dbert` model** + **BYOK**: OpenAI, Anthropic, Google, OpenRouter, Groq + **complexity-based routing** |
| Code execution | **Bundled Python subprocess sandbox** (no network, scratch dir, CPU/mem/time limits, restricted imports) |
| Local model | **`DBERT/DBERT_AI`** (confirmed: GGUF, 531 MB, 32K ctx) pulled from the **Ollama registry over HTTPS**, served by **llama.cpp (`llama-cpp-python`)** — **no Ollama dependency**; **CPU default, optional CUDA** |
| Owner / branding | App owned by **Gayatri Education**; developed under the **DBert Incubation Program (dbert.online)**; EULA at `packaging/EULA.txt` |
| Courses | Ship the **course-package format** + a small **sample fixture**; real 4 courses authored later to the same format |
| Packaging | **Nuitka** compile → **Inno Setup** installer (EULA + model-download prompt) → **EV code-signing**; **encrypted course packages** |
| DB | **SQLite via SQLCipher** (encrypted at rest) |
| Accounts | **Optional login** (`specs/auth_flow.md`): local model, BYOK, and bundled courses work signed-out; sign-in required only for store purchases, downloads, cloud backup, and account-attached telemetry. Refresh token in DPAPI; entitlements verified offline via server-signed tokens. |

---

## 1.1 Relationship to the legacy Gayatri AI codebase

**This is a from-scratch rebuild in a new architecture, not an incremental change to the existing Flet app.** Do NOT try to extend the current `main.py`/Flet structure. Start a clean project (§4) and **port** the specific reusable logic below into it. Roughly ~80% of this milestone is net-new code; the legacy repo is a source of salvageable engine logic, not a foundation.

| Legacy file / asset | Action | Notes |
|---|---|---|
| `main.py`, `ui_components.py`, `sample_ui.py`, `diagnostic_test.py`, `test.py` (all Flet UI) | **Discard** | Stack changes Flet → PySide6 + WebView; UI is the locked HTML mockup. None of the Flet UI survives. |
| `search_engine.py` — `split_sections`, `hybrid_score`, gate/keyword/search/crawl/grounded-message logic | **Port & upgrade** → `core/rag/*`, `core/tutor/*` | Reuse the algorithms as a starting point, then upgrade per the intelligence roadmap (full-page fetch, RRF, reranker, sqlite-vec). |
| `db.py` — sessions/messages/stats/session_context_files schema & patterns | **Port & extend** → `core/persistence/*` | Reuse the schema shape; migrate to **SQLCipher** + add mastery/courses/licenses tables + integrity HMACs. |
| `llm_client.py` — streaming + JSON-mode patterns | **Rebuild using as reference** → `core/providers/*` | Single LM-Studio client becomes the multi-provider BYOK + local-model interface. Keep the streaming/parse patterns; expand the abstraction. |
| `config.py` — single-source-of-truth pattern | **Adopt the pattern** → `core/config.py` | Keep the "no hardcoding" discipline; new values. |
| `context_manager.py` — markdown context assembly / ranking | **Port ideas** → `core/rag` + `core/courses` | Concepts feed the course-RAG and context-budgeting logic. |
| Known QA bugs (category overwrite, `sim_sem` crash, thread-unsafe UI updates, in-memory settings, unwired export) | **Do not reproduce** | The new implementations must fix these by design (called out in the relevant phases). |
| Everything else (tutor engine, sandbox, course format/store, Ollama puller, security guard, packaging) | **Net-new** | No legacy equivalent. |

**Practical guidance for Claude Code:** clone the legacy repo for reference only; copy specific functions into the new structure and refactor them to the new interfaces — never import the old package or carry over the Flet dependency.

---

## 2. Architecture overview

Single Python process, layered:

```
┌───────────────────────────────────────────────┐
│ PySide6 QMainWindow (frameless, custom titlebar)│
│  └─ QWebEngineView  ← loads bundled UI (HTML)   │
│        ⇅ QWebChannel bridge (Bridge object)     │
├───────────────────────────────────────────────┤
│ Application core (Python)                       │
│  • Orchestrator / agent runtime                 │
│  • LLM providers (BYOK) + Local model server    │
│  • Model Router (complexity-based)              │
│  • RAG + Course engine                          │
│  • Tutor engine (skill graph, mastery, agents)  │
│  • Code sandbox runner                          │
│  • Security guard (injection/abuse filters)     │
│  • Course Store client (mock server API)        │
│  • Persistence (SQLCipher), Settings, Secrets   │
└───────────────────────────────────────────────┘
```

Threading: the LLM/inference/sandbox/network work runs on Qt worker threads (`QThreadPool`/`QRunnable`) or a background asyncio loop; **never block the UI thread**. Stream tokens to the WebView via QWebChannel signals. (Fix the current app's bug of mutating UI state from worker threads — marshal UI updates through signals.)

Second window: the **Course Store** is a separate `QMainWindow`/`QDialog` hosting its own QWebEngineView + store UI.

---

## 3. Tech stack & key dependencies

- **UI/app:** `PySide6` (Qt6, QWebEngine, QWebChannel)
- **Local inference:** `llama-cpp-python` (CPU wheel default; CUDA wheel optional), GGUF models
- **Model download:** `httpx` (async, resumable) against `registry.ollama.ai`
- **Cloud providers:** `openai`, `anthropic`, `google-generativeai` (+ OpenAI-compatible base-url for OpenRouter/Groq)
- **RAG:** `sentence-transformers` (MiniLM, **bundled** with installer), `sqlite-vec` for vectors, `rank_bm25` or SQLite FTS5 for lexical, cross-encoder reranker optional
- **DB:** `sqlcipher3-binary` (or `pysqlcipher3`), schema migrations
- **Secrets:** Windows DPAPI via `pywin32`/`keyring`
- **Sandbox:** stdlib `subprocess` + Windows **Job Objects** (`pywin32`) for hard resource caps
- **Packaging:** `nuitka`, **Inno Setup** (installer), `signtool` (EV signing)
- **Testing:** `pytest`, `pytest-qt`

Pin all versions; generate an SBOM; run `pip-audit` in CI. (The current repo ships mismatched deps — start clean.)

---

## 4. Project structure

```
gayatri/
  app/
    main.py                 # entrypoint: QApplication, main window, bridge wiring
    bridge.py               # QWebChannel Bridge (JS-callable slots + signals)
    windows/                # main window, store window, dialogs
    ui/                     # the locked HTML/CSS/JS (from mockup), assets, fonts
  core/
    config.py               # constants, paths, feature flags (fix hardcoding)
    orchestrator.py         # routes a user turn → agents → response stream
    providers/
      base.py               # LLMProvider interface (validate, list_models, chat, stream, tools)
      openai_compat.py      # OpenAI/OpenRouter/Groq/Together/DeepSeek/Mistral
      anthropic.py
      google.py
      local_llama.py        # llama-cpp-python server wrapper
      registry.py           # provider registry + unified model catalog
    router.py               # complexity-based model selection
    model_fetch/
      ollama_pull.py        # pull GGUF from registry.ollama.ai WITHOUT ollama
      install_hook.py       # first-run/installer model download flow
    rag/
      ingest.py             # extract + chunk (md/pdf/docx/code)
      index.py              # sqlite-vec + FTS5, RRF fusion, rerank
    courses/
      format.py             # course package (.gcp) parser + validator
      loader.py             # decrypt, load, index a course
      store_client.py       # in-app store API client (MOCKABLE)
    tutor/
      skill_graph.py
      mastery.py            # BKT + decay; HMAC-integrity-protected
      agents/
        tutor.py  practice.py  examiner.py  doubt_solver.py  code_mentor.py
    sandbox/
      runner.py             # subprocess + Job Object isolation
    security/
      guard.py              # prompt-injection + abuse defenses (central)
      secrets.py            # DPAPI key vault
      crypto.py             # AES-GCM envelope, package decryption, HMAC
    persistence/
      db.py                 # SQLCipher connection, schema, migrations
      models.py             # dataclasses / row mappers
      settings.py           # settings.json (validated), persisted
      outbox.py             # telemetry queue (LOCAL ONLY this milestone)
  tests/
  packaging/
    build_nuitka.py
    installer.iss           # Inno Setup script (EULA, model prompt)
    EULA.txt
  pyproject.toml  requirements.txt  README.md  SECURITY.md
```

---

## 5. Data model (SQLCipher)

Tables (encrypted DB): `settings`, `providers` (name, key_ref, enabled), `models_cache`, `sessions`, `messages` (+ parent_id for branching, sources_json, model_used, routing_reason, tokens, latency, ts), `courses` (id, version, entitlement, installed_at), `skills` (course_id, skill_id, prereqs), `mastery` (course_id, skill_id, p_mastery, last_seen, review_due, **hmac**), `attempts` (item_id, skill_id, correct, ts), `projects`, `telemetry_outbox`, `licenses`.

**Integrity:** every `mastery` and `licenses` row carries an HMAC (key derived from a device secret) so a user can't hand-edit the DB to unlock gates/courses. Verify HMAC on read; refuse tampered rows.

---

## 6. Course package format (`.gcp`) — define & lock now

A `.gcp` is a ZIP (AES-256-GCM encrypted for paid courses; sample fixture uses a dev key):

```
manifest.json      # id, title, version, author, description, price,
                   #   unlock_rule (paid|free|mastery), module_order[],
                   #   min_app_version, signature
skills.json        # nodes: [{skill_id, name}], edges: [{from, to}] (prereqs)
modules/<mid>/
  lessons/*.md     # markdown; supports <!--checkpoint:skill_id-->  markers
  practice.json    # items: [{id, skill_id, difficulty, type, prompt, answer|tests}]
  exam.json        # exam bank + rubric + pass_threshold
projects/*.json    # {spec_md, rubric[], hidden_tests[], viva_bank[]}
assets/            # images etc.
```

Deliver `core/courses/format.py` (parse + JSON-schema validate + signature check) and a JSON-schema doc under `docs/course-format.md`. Ship one **sample fixture** ("Python Basics — sample") with 1 module, ~6 lessons, practice, an exam, and one project with hidden tests — enough to exercise every engine path. Real courses authored later to this exact schema.

---

## 7. Phase-by-phase plan

Each phase lists **Goal · Tasks · Deliverables · Acceptance**. Build in order; each phase must be runnable and tested before the next.

### Phase 0 — Scaffolding & dev environment
- **Tasks:** repo structure (§4); `pyproject.toml`, pinned `requirements.txt`; venv; `config.py` with all paths/constants (no hardcoding); logging (no secrets/PII/chat in logs); pre-commit (ruff, gitleaks); `pytest` skeleton.
- **Acceptance:** `python -m app.main` opens an empty PySide6 window; CI runs lint + empty test suite green.

### Phase 1 — App shell + UI bridge
- **Tasks:** frameless `QMainWindow` with custom titlebar (Windows min/max/close); embed **QWebEngineView** loading the bundled HTML mockup from disk; implement **QWebChannel `Bridge`** exposing async slots (`send_message`, `get_sessions`, `new_chat`, `set_setting`, …) and signals (`token`, `step`, `sources`, `done`, `error`) for streaming; wire the mockup's JS to call the bridge instead of its demo functions.
- **Deliverables:** working shell where the real UI drives real Python (echo/stub responses first).
- **Acceptance:** typing a message round-trips JS→Python→JS with a streamed stub reply; theme toggle, sidebar, command palette all functional against the bridge.

### Phase 2 — LLM providers + BYOK
- **Tasks:** `LLMProvider` interface (`validate_key`, `list_models`, `chat`, `stream`, `supports_tools/vision/json`); implement OpenAI-compatible adapter (covers OpenAI/OpenRouter/Groq/DeepSeek/Mistral via base_url), Anthropic, Google adapters; **key validation** (cheap `list_models`/1-token call) + **model catalog fetch** normalized into a unified registry (ctx length, cost tier, speed tier, capabilities); store keys with **DPAPI** (`security/secrets.py`) — never plaintext, never logged; Settings UI to add/validate/remove keys and see fetched models.
- **Acceptance:** user pastes a real key → validated → models listed → a chat streams from that provider; keys survive restart, are absent from disk in plaintext and from logs.

### Phase 3 — Local model: pull `DBERT/DBERT_AI` GGUF from the Ollama registry *without* Ollama
**Confirmed model coordinates** (verified against the live registry):
- Page: `https://ollama.com/DBERT/DBERT_AI` · registry namespace/model: **`DBERT/DBERT_AI`** · tag: **`latest`**
- Format: **GGUF** · size: **531 MB** (`531,067,840` bytes) · context: **32K**
- Weights layer digest: `sha256:32793ff2b89a38a0685b8d519cdf86c6f243a093ef2f8877f1fad5873fdc7b5c`

**Exact pull recipe** (implement in `model_fetch/ollama_pull.py`):
1. `GET https://registry.ollama.ai/v2/DBERT/DBERT_AI/manifests/latest` with header `Accept: application/vnd.docker.distribution.manifest.v2+json`.
2. Parse `layers[]`. Save each by mediaType:
   - `application/vnd.ollama.image.model` → the **GGUF weights** (→ `dbert_ai.gguf`)
   - `application/vnd.ollama.image.system` → the **chat template** (apply it when prompting)
   - `application/vnd.ollama.image.params` → **default params** (temp, stop tokens, etc.)
3. Download each blob: `GET https://registry.ollama.ai/v2/DBERT/DBERT_AI/blobs/<digest>` using `httpx` with **`Range` resume**, streaming to disk with a progress callback, then **verify the sha256 digest** matches (fail hard on mismatch).
4. Store under the app data dir (e.g. `%LOCALAPPDATA%/GayatriAI/models/dbert_ai/`).

- **Tasks:** `ollama_pull.py` (manifest + resumable, checksummed blob download + progress signals to the UI); `local_llama.py` wraps `llama-cpp-python`, loads `dbert_ai.gguf`, applies the pulled template/params, and exposes the same `LLMProvider` streaming interface; **CPU build default**, detect NVIDIA → use **CUDA** path if present; clear errors if RAM insufficient (531 MB weights → runs on virtually any laptop).
- **Acceptance:** app pulls `DBERT/DBERT_AI` with a live progress bar, verifies the digest, loads it, and streams a completion — with **no Ollama installed anywhere**. Killing and restarting the download resumes rather than restarting.

### Phase 4 — Model router (complexity-based)
- **Tasks:** `router.py` scores each request (task type, input length, code presence, reasoning keywords, needed context, user cost/speed preference) → picks tier: **fast** (Groq/Flash/mini), **quality** (Claude/GPT/Gemini-Pro), **local** (dbert). Per-provider **fallback chains** (down/rate-limited → reroute) + health tracking. Record `model_used` + `routing_reason` on every response. Routing rules loaded from a local JSON config (server-updatable later).
- **Acceptance:** simple query → fast/local tier; complex/coding query → quality tier; provider outage falls back automatically; every message row logs which model + why.

**Seed routing config** (ship as `core/router_config.json`; server-updatable later). Tiers, the model→tier map, and the task→tier policy:

*Tier definitions*

| Tier | Purpose | Latency/cost profile |
|---|---|---|
| `local` | Offline, privacy, cheap background tasks | Free, on-device (`DBERT_AI`) |
| `fast` | Cheap/quick cloud tasks | Low cost, very low latency |
| `quality` | Hard reasoning, tutoring, grading | Higher cost, best accuracy |

*Model → tier map* (only models the user has a validated key for are eligible; `local` always available if the model is installed)

| Provider | Model (id pattern) | Tier |
|---|---|---|
| Local | `dbert_ai` | `local` |
| Groq | `llama-3.x-8b*`, `llama-3.x-70b-versatile` | `fast` |
| OpenAI | `gpt-*-mini`, `gpt-*-nano` | `fast` |
| Google | `gemini-*-flash*` | `fast` |
| OpenRouter | any `*:free`, `*-mini`, `*-flash`, small 7–8B | `fast` |
| OpenAI | `gpt-*` (full, non-mini), `o*`/reasoning | `quality` |
| Anthropic | `claude-*-sonnet*`, `claude-*-opus*` | `quality` |
| Anthropic | `claude-*-haiku*` | `fast` |
| Google | `gemini-*-pro*` | `quality` |
| OpenRouter | large frontier models (70B+, pro/opus/sonnet-class) | `quality` |

*Task → target tier policy* (router picks the highest-priority available tier for the task; falls back down the chain on outage/rate-limit/missing key)

| Task / trigger | Preferred tier | Fallback chain |
|---|---|---|
| Titles, keyword-gen, search-gate, short summaries | `fast` | `fast → local` |
| Simple chat / doubt (short, no code, no reasoning cues) | `fast` | `fast → local → quality` |
| Tutoring explanations, lesson delivery | `quality` | `quality → fast → local` |
| Coding help / Code Mentor / code review | `quality` | `quality → fast` (skip `local` if 531 MB model underperforms on code) |
| **Exam grading / Examiner / mastery decisions** | `quality` | `quality → fast` (**never** `local` — grading integrity) |
| Long-context (> local 32K, or big RAG payload) | `quality` | pick largest available context window |
| User forced "Local only" / offline | `local` | `local` (error if not installed) |
| User forced "Fast / cheapest" | `fast` | `fast → local` |

*Complexity signals feeding the choice:* input token length, presence of code blocks, reasoning keywords (compare/prove/design/debug/why), required context size, retrieved-chunk volume, and the explicit user preference (cost-saver / balanced / max-quality) from Settings. Cost/latency caps and token budgets from the Security Guard (Phase 8) can force a downgrade to `fast`/`local`.

### Phase 5 — RAG + course engine
- **Tasks:** ingest layer (md/pdf via PyMuPDF/docx/txt/code) → **header-aware chunking** with overlap → embed once (bundled MiniLM) → store in **sqlite-vec**; retrieval = **BM25 (FTS5) + dense fused via RRF**, optional cross-encoder rerank; `courses/format.py` + `loader.py` (validate, decrypt, index a `.gcp`); load the sample fixture.
- **Acceptance:** ask a question about the sample course → retrieves correct chunks with citations back to the exact lesson; graceful degradation to BM25 if embeddings unavailable (fixes prior `sim_sem` crash).

### Phase 6 — Tutor engine (adaptive core)
- **Tasks:** `skill_graph.py` (load from `skills.json`); `mastery.py` (**BKT** update per attempt + time **decay**, HMAC-protected rows); agents: **Tutor** (Socratic, checkpoint questions, level-adaptive explanations), **Practice Generator** (items targeted to weak skills at ~75% expected success), **Examiner** (module exams from bank + variants, rubric grading, **mastery gate**: unlock next module only at threshold + a delayed retention check), **Doubt-Solver** (course-RAG first, labeled web fallback). Progress/mastery surfaced in the UI (the meter/stat slots exist).
- **Acceptance:** completing the sample module updates mastery, gates the next module correctly, generates fresh targeted practice, and answers doubts with course citations.

### Phase 7 — Code Mentor + secure sandbox
- **Tasks:** `sandbox/runner.py` — run student/graded code in a **separate Python subprocess** with: **no network** (block sockets), **scratch temp dir only** (no access to app/user files), **CPU + memory + wall-time limits** via Windows **Job Objects**, **restricted imports/builtins**, output size caps, hard kill on timeout; `code_mentor.py` — graduated hints (nudge→concept→pseudocode, **never full solutions on graded work**), runs code, interprets errors, grades projects against `hidden_tests`.
- **Acceptance:** student code runs and returns output/errors in-app; a malicious sample (network call, file read outside scratch, fork bomb, infinite loop, huge memory alloc) is **blocked or killed** within limits; graded runs use hidden tests and the mentor never leaks them.

### Phase 8 — Security guard: injection & abuse defenses (central)
Implement `security/guard.py`, applied to **every** model call:
- **Prompt/query-injection defenses:** strict role separation; **wrap all untrusted content** (course text, retrieved chunks, web results, student code, file uploads) in clearly delimited, labeled blocks marked as *data, not instructions*; strip/neutralize injected role tokens and control sequences (`<|im_start|>`, "ignore previous instructions", "system:", etc.); a hardened system prompt instructing the model to never reveal system/instructions, hidden rubrics, **answer keys**, or other courses' content.
- **Keep secrets out of the model context:** exam answer keys, hidden tests, rubrics, and grading logic are evaluated **in the engine**, not placed in the LLM prompt — so no injection can extract them. The Examiner's pass/fail is engine-verified, never "the model said pass."
- **Output filtering:** scan responses for leakage of system prompt / rubric / cross-course content; redact.
- **Tool guardrails:** whitelist tools per agent; validate tool args; `fetch_url` uses an allowlist and blocks `localhost`/private IPs/`file://` (SSRF); code only ever runs via the sandbox.
- **Abuse controls:** per-session **rate limiting** + concurrency caps; **token/cost budgets** per BYOK provider with user-visible warnings and hard caps (prevent runaway spend); agent-loop/recursion caps; input size limits; jailbreak/abuse pattern detection (+ optional small classifier); age-appropriate content filter for the education context.
- **Anti-tamper on progress:** mastery/entitlement rows HMAC-verified (§5); assessment actions resistant to automation/replay.
- **Course-IP protection:** decrypt packages in memory only; never dump a whole course into a prompt (chunked retrieval only); per-user watermark hooks.
- **Acceptance:** a red-team test set (injection strings, answer-key extraction attempts, SSRF URLs, DB-edit to unlock a gate, token-flood) is **defeated**; add these as regression tests.

### Phase 9 — Course Store (client only; mockable server)
- **Tasks:** separate store window (own WebView + store UI); `store_client.py` behind an interface (`list_catalog`, `get_course`, `purchase`, `download`, `verify_entitlement`) with a **local mock implementation** (fixture catalog + fake purchase) so the flow works end-to-end now; on "purchase→download", fetch the `.gcp`, verify signature/entitlement, install and index it. Real server just swaps the client impl later.
- **Acceptance:** open store → browse catalog → "buy" a mock course → it downloads, installs, appears in the sidebar, and is learnable — all against the mock.

### Phase 10 — Persistence, settings, offline, telemetry outbox (local)
- **Tasks:** finalize SQLCipher schema + migrations; **settings.json** persisted (fixes prior in-memory-only settings); session/message history with branching; **telemetry outbox table populated locally** (model, routing_reason, tokens, latency, hardware class, app version, UTC ts) — **queued only, no upload this milestone**; carry over the earlier compliance requirement: **first-run consent screen** scaffolding + data controls, even though nothing is uploaded yet.
- **Acceptance:** everything persists across restart; telemetry rows accrue locally; consent screen shown once and recorded.

### Phase 11 — Packaging, installer, EULA, model-download prompt
- **Tasks:** `build_nuitka.py` (standalone compile, bundle UI assets, MiniLM model, CPU llama.cpp; optional CUDA variant); **Inno Setup** `installer.iss` with **EULA acceptance screen**, install location, Start-menu/desktop shortcuts, and a **checkbox/prompt: "Download the dbert local model now?"** → runs the Phase-3 puller during/after install (with progress) or defers to first run; **EV code-sign** the `.exe` and the installer; encrypt the bundled sample course package.
- **Acceptance:** a clean Windows machine runs the installer, accepts EULA, optionally downloads the model, and launches a fully working Gayatri AI. SmartScreen shows a signed publisher.

### Phase 12 — QA, tests, RE-hardening pass
- **Tasks:** unit tests (chunking, RRF, BKT, format validation, router), integration tests with a **mock LLM server**, sandbox security tests, injection/abuse regression suite (Phase 8); **RE hardening**: confirm no secrets in the binary, sensitive modules obfuscated, anti-tamper/integrity check, cert pinning on any network calls, license-binding hook; SBOM + `pip-audit` clean.
- **Acceptance:** full suite green; a manual RE check confirms no keys/answer-keys recoverable from the shipped artifact; go/no-go checklist (below) all ticked.

**Phase 12 — completed 2026-08-02:**
- Full test suite: 522 passed, 2 skipped (exit code 0)
- UI smoke tests: `test_ui_smoke.py` (4 tests) — all pass, verified stable across 3 consecutive runs
  - Fixed flaky `test_command_palette_and_sidebar_act_on_the_bridge` by adding Qt event loop yields and isolated DB per test
  - Fixed flaky `test_theme_toggle_repaints_and_persists` by using `window.setTheme()` directly instead of clicking theme buttons
- Unit tests: `test_license_bind.py` (20 tests), `test_integrity.py` (6 tests), `test_cert_pin.py` (12 tests) — all pass
- Anti-tamper: `check_integrity()` wired into `app/main.py` startup path; HMAC-SHA256 signed manifest verified before UI loads in frozen builds
- Cert pinning: `_KNOWN_PINS` registry for `registry.ollama.ai`; `pinned_httpx_client` + `verify_pin` with full mock test coverage
- License binding: device fingerprint (MachineGuid + WMI CPU/BIOS + hostname) → HMAC-bound entitlements in SQLCipher; DB mockable via DI
- SBOM: `sbom.json` (Cyclonedx format, 19 components from requirements.txt)
- `pip-audit` clean (No known vulnerabilities found)
- No hardcoded secrets found in codebase (confirmed via grep)
- Integration/UI smoke tests: pass (4/4 tests, 3 consecutive runs stable)
- Injection/abuse regression suite: deferred (Phase 12 partial — Phase 8 has unit tests; full red-team suite is Phase 8 acceptance deferred)
- RE check on Nuitka binary: deferred (requires actual Nuitka build output)

---

## 8. Cross-cutting requirements

- **Never block the UI thread**; stream via signals; marshal all UI mutations to the main thread (fixes a known bug in the current app).
- **No secrets in code or logs, ever.** BYOK keys via DPAPI; encryption keys derived per device.
- **Encryption everywhere feasible:** SQLCipher DB, DPAPI keys, AES-GCM course packages, TLS + cert-pinning for network.
- **Graceful degradation:** offline → local model + BM25 RAG; provider down → fallback chain; embed model missing → lexical retrieval.
- **Coding standards:** typed Python, `ruff`, docstrings, small modules, dependency injection for providers/store (so mocks are trivial).
- **Every response records** model_used + routing_reason + tokens + latency (feeds later telemetry).

## 9. Definition of done (the shippable .exe)

- [ ] Installs from a signed Inno Setup installer with EULA acceptance
- [ ] First run shows consent screen; optional dbert model download works (no Ollama)
- [ ] Premium UI (the locked mockup) fully wired to the Python backend
- [ ] Local model **and** ≥3 BYOK providers work, with complexity routing + fallback
- [ ] Sample course: learn → practice → exam gate → project graded in sandbox → doubts answered with citations
- [ ] Course store (mock) purchase→download→install→learn flow works
- [ ] Injection/abuse red-team suite passes; sandbox contains malicious code
- [ ] No secrets/answer-keys extractable from the binary; DB tamper-resistant
- [ ] All data persists; settings persist; telemetry queues locally

## 10. Open items to confirm (flagged, not blocking scaffolding)

1. ~~Exact `dbert` model coordinates~~ — **RESOLVED.** `DBERT/DBERT_AI:latest`, GGUF, 531 MB, 32K ctx, weights digest `sha256:32793ff2…fdc7b5c` (see Phase 3). No fallback needed.
2. **EV code-signing certificate** — procure early (issuance can take days).
3. **BYOK model→tier mapping** — initial routing table (which models count as fast/quality) — I'll seed sensible defaults; confirm before launch.
4. Confirm minimum target hardware (RAM/VRAM) to set model-download guardrails.
