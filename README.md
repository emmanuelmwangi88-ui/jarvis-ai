# JARVIS (local edition)

A local, tool-using AI personal assistant built on your Ollama models: a clean chat UI,
local voice in/out, persistent memory, local RAG, and real control over your machine —
files, terminal, app windows, clipboard, browser, email, and websites. Everything runs
on your hardware; nothing phones home.

> **On "better than Claude":** a 1B–4B local model won't out-reason a frontier cloud
> model — but on the axes that matter for a *personal* assistant (acting on your machine,
> privacy, always-on, memory of you, low latency) this genuinely beats a cloud chatbot.
> The full, honest breakdown and the path to close the quality gap is in
> [`docs/roadmap.md`](docs/roadmap.md).

## Quick start

```bash
# 1. Install Ollama (https://ollama.com) — launch.py starts it for you if needed.
# 2. Pull the models (you already have these):
ollama pull llama3.2         # 3B primary brain (llama3.2:latest)
ollama pull llama3.2:1b      # tiny/fast for greetings + review
ollama pull qwen2.5-coder:3b # code
ollama pull gemma3:4b        # reasoning / long-form (multi-model mode)
ollama pull moondream:1.8b   # vision
ollama pull nomic-embed-text # RAG embeddings
# 3. Install deps:
pip install -r requirements.txt
# 4. Run:
python launch.py        # fullscreen window (falls back to your browser)
python cli.py           # terminal-only, no UI
```

Full instructions, env vars, and troubleshooting: [`docs/setup.md`](docs/setup.md).

## Project layout

```
jarvis/
  launch.py            run this: opens the fullscreen chat window
  cli.py               optional: terminal-only, no UI
  requirements.txt
  core/                the brain
    config.py            models per role, autonomy, workspace lock, voice, email
    ollama_check.py      auto-connect/start Ollama; chat() + embed() wrappers
    model_router.py      picks a model per message
    agent.py             the routing + tool-calling loop (handle_message)
    memory.py            SQLite conversation history + notes
    rag.py               local knowledge store (nomic-embed-text)
    voice.py             faster-whisper (speech-in) + Piper (speech-out)
  tools/
    tools.py             every real action + the schema Ollama uses to call them
  ui/
    ui_server.py         FastAPI backend (chat, voice, status endpoints)
    static/index.html    the chat interface
  docs/                  full documentation (see below)
```

## Documentation

Organized in [`docs/`](docs/README.md):

- [Architecture](docs/architecture.md) — how a message flows end to end
- [Setup](docs/setup.md) — install, configure, run, troubleshoot
- [Frontend](docs/frontend.md) — the chat UI, status, confirmations, voice
- [Backend](docs/backend.md) — FastAPI + the agent brain, memory, RAG, voice
- [API reference](docs/api-reference.md) — every endpoint with examples
- [Tools](docs/tools.md) — every capability + how to add your own
- [Safety](docs/safety.md) — gates, workspace lock, autonomy, what "local" means
- [Roadmap](docs/roadmap.md) — the honest "better than Claude" answer

## The interface — JARVIS Core

An agent-forward UI (aurora teal/emerald/gold) built around a **live reactor orb** that
reacts to what the AI is doing (idle → thinking → acting → speaking → listening):
- **Streaming replies** (`/api/chat/stream`, SSE) — tokens appear as they generate, so a
  small local model *feels* as responsive as a cloud assistant.
- **Autonomy switcher** — Locked / Trusted / **Unleashed** (one click, with a warning);
  Unleashed removes all guardrails except email confirmation.
- **Self-learning panel** — shows skills the agent has taught itself (`learn` tool) and a
  live count; a ⚡ button triggers reflect-and-learn.
- **Live telemetry** (tokens/s, CPU, memory), an **Activity Stream** of every tool call,
  capability chips that gate tools in real time, hold-to-talk **voice**, and a **⌘K
  command palette**.

Everything is wired to real backend data — see [`docs/frontend.md`](docs/frontend.md).
One self-contained `ui/static/index.html` (inline SVG, graceful font fallback), so it
renders even without a network.

> Speed & quality: the agent uses `keep_alive`, single-model mode, capped generation, and
> **streaming** so replies start fast and read well. On raw reasoning it still won't beat
> Claude (a 3–4B local model can't) — but it's fast, private, always-on, acts on your
> machine, and gets sharper as it learns. The honest breakdown + a one-module cloud-hybrid
> path is in [`docs/roadmap.md`](docs/roadmap.md).

## How it works (one paragraph)

Your message hits the FastAPI backend, which calls `agent.handle_message()`. A tiny
keyword/length **router** picks the right model role — primary chat (`llama3.2:latest`),
explicit code (`qwen2.5-coder:3b`), reasoning (`gemma3:4b`), or vision (`moondream:1.8b`)
— while keeping one model hot in RAM for speed. The agent runs a **tool-calling loop**:
the model can call any function in `tools/tools.py` (including **`web_search`**), JARVIS
executes it, feeds the result back, and repeats until the model answers. Risky shell
commands get a fast second opinion and **wait for your yes**; sending email always
confirms. Saved **notes** and a local **RAG** store give it memory of you across sessions.

## Model routing

Tuned for the models you have installed. **Single-model mode** (default, for 8GB RAM)
keeps one model hot — see [`docs/performance.md`](docs/performance.md).

| Task type | Model | Trigger |
|---|---|---|
| Primary / chat / web / general tools | `llama3.2:latest` (3B) | default — good answers, fast, reliable tool calling |
| Trivial greetings / acks | `llama3.2:1b` | "hi", "thanks", very short messages |
| Explicit coding | `qwen2.5-coder:3b` | keywords like "code", "python", "debug", "regex" |
| Long / analytical (multi-model mode) | `gemma3:4b` | "why", "compare", "design", or messages over ~220 chars |
| Screen questions | `moondream:1.8b` | "screenshot", "screen", "what do you see" — direct vision call, bypasses the tool loop |
| Risky command review | `llama3.2:1b` | automatic, only at the confirmation gate (fast) |

In multi-model mode (`JARVIS_SINGLE_MODEL=0`) web/tool turns use `qwen2.5-coder:3b` and
analytical turns use `gemma3:4b` for higher per-task quality at the cost of model reloads.

**Web search:** `web_search(query)` hits DuckDuckGo (no API key) and the model is
instructed to use it for anything current, factual, or uncertain, then read the best
result with `fetch_url`. `remember_document(path)` / `search_knowledge(query)` use
`nomic-embed-text` for local RAG over your own files.

## Safety model (summary)

- **Read-only tools** (search, read, list) run immediately.
- **Risky terminal commands** get a fast `llama3.2:1b` review and require your `yes`
  (`AUTONOMY="yolo"` skips this — not recommended).
- **Sending email is always confirmed.**
- **File overwrites** require `overwrite=true`.
- **`WORKSPACE_ROOT`** confines file tools to one folder. Details: [`docs/safety.md`](docs/safety.md).

## Self-improvement (the honest version)

`remember()` saves notes that carry into future sessions; `reflect_and_remember()` runs
automatically every 6 turns to extract lessons on its own. This is **accumulated context,
not model retraining** — the real fine-tuning path is in [`docs/roadmap.md`](docs/roadmap.md).

## Honest limitations

- Local 1B–4B models aren't Claude/GPT-4-class at reasoning, coding, or writing. This is a
  genuinely useful *tool-using agent for your machine*, not a bigger brain.
- 8GB RAM is tight — route to `llama3.2:1b` more aggressively if replies are slow.
- "Plan before acting" is a prompt-level instruction; the code-enforced guardrails are the
  confirmation gates and workspace lock.
- Real self-modifying/fine-tuned learning is a separate, manual project (see the roadmap).
- `pywinauto` window control and `os.startfile` are Windows-only; other tools are
  cross-platform.

## Extending it

Add a capability: write a function in `tools/tools.py`, add its JSON schema to
`TOOLS_SCHEMA`, register it in `TOOL_FUNCTIONS`. The model uses it automatically next run
— no changes needed in `core/agent.py`. See [`docs/tools.md`](docs/tools.md).
