# Gayatri AI

**Local-first agentic AI platform with fine-tuned  model.**

A desktop application where a locally-running LLM acts as the brain — tutoring students, orchestrating specialized agents, and calling cloud APIs when needed. Everything runs locally first.

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python -m app.main
```

## Project Structure

```
gayatri/
  core/
    config.py           — all constants, paths, feature flags
    logging_setup.py    — rotating logs, PII/credential redaction
    providers/
      local.py          — llama-cpp-python wrapper for GGUF models
    agents/
      registry.py       — agent registration & dispatch
      runtime.py        — agent execution loop, tool dispatch
    security/
    persistence/
    rag/
    courses/
    tutor/
    sandbox/
  app/
    main.py             — entrypoint
    bridge.py           — QWebChannel Bridge (JS ⇄ Python)
    windows/
      main_window.py    — frameless QMainWindow
    ui/
      index.html        — premium UI
  training/
    generate_data.py    — training data generation
    colab_notebook.py   — Colab fine-tuning script
    processed/
      train.jsonl       — training data
      val.jsonl         — validation data
  tests/
    conftest.py
    test_agent_registry.py
```

## Model Training Pipeline

1. **Generate data** — `python training/generate_data.py` (produces 1355+ examples)
2. **Fine-tune on Colab** — Upload `colab_notebook.py`, run cells top to bottom
3. **Download GGUF** — Get the final `.gguf` file from Colab
4. **Drop into app** — Place GGUF at `%LOCALAPPDATA%\GayatriAI\models\`
5. **Run locally** — `python -m app.main`

## Tech Stack

| Component | Technology |
|---|---|
| UI | PySide6 + QWebEngine + QWebChannel |
| Local LLM |  fine-tuned → GGUF → llama-cpp-python |
| Training | QLoRA on Colab (Unsloth) |
| Database | SQLite + FTS5 + sqlite-vec |
| Secrets | Windows DPAPI |
| Testing | pytest, pytest-qt |
| Linting | ruff |

## Status

**Phase 1 — Foundation:** Project scaffold, config, logging, app shell, bridge, agent registry. ✅

## License

**Educational / Personal Use Only — Commercial Use Prohibited**

This repository is publicly available for educational, academic, research, and personal learning purposes.
You are welcome to read and study the source code and make modifications for your own non-commercial educational or personal use.

Commercial use, redistribution, resale, incorporation into commercial products or services, SaaS deployment, and development of competing commercial products are not permitted without prior written permission from Gayatri Education.

See the [LICENSE](LICENSE) file for the complete terms.

Copyright © 2026 Gayatri Education. All Rights Reserved.
