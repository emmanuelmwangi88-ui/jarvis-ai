# Architecture

Sakura AI is three layers over your local Ollama server: a **frontend** (a single HTML
page), a **backend** (FastAPI), and a **brain** (the agent loop + supporting modules).
A parallel **CLI** reuses the exact same brain with no server involved.

## Directory map

```
jarvis/
  launch.py            # entry point: start Ollama → start backend → open window
  cli.py               # terminal-only front end (same brain, no server)
  requirements.txt

  core/                # the brain + infrastructure
    config.py          # all settings: models, autonomy, workspace lock, voice, email
    ollama_check.py    # connect/auto-start Ollama; chat() + embed() wrappers
    model_router.py    # map a message → a model role (chat/tools/reason/vision)
    agent.py           # handle_message(): route → chat → tools → loop; reflection
    memory.py          # SQLite conversation history + durable notes
    rag.py             # local knowledge store (chunk → embed → cosine search)
    voice.py           # faster-whisper (STT) + Piper (TTS), imported lazily

  tools/
    tools.py           # every real action + TOOLS_SCHEMA + TOOL_FUNCTIONS registry

  ui/
    ui_server.py       # FastAPI: /, /api/status, /api/chat, /api/voice, /api/reflect, /api/reset
    static/index.html  # the chat interface (self-contained HTML/CSS/JS)

  docs/                # you are here
```

## Request lifecycle (text chat)

1. **Frontend** posts `{ text, confirm }` to `POST /api/chat`.
2. **Backend** (`ui_server.chat`) calls `agent.handle_message(text, confirm)`.
3. **Router** (`model_router.route`) picks a *role* from keywords + length:
   `vision` · `tools` · `reason` · `chat`. Each role maps to a concrete Ollama model.
4. **Vision short-circuit:** a screen question skips the tool loop — it takes a
   screenshot and asks the vision model directly.
5. **Agent loop** (up to `MAX_TOOL_ITERATIONS`):
   - Build messages = system prompt + saved notes + recent history + the new message.
   - Call `ollama_check.chat(model, messages, tools)`.
   - If the model returns **no tool calls** → that's the reply; persist and return.
   - If it returns **tool calls** → for each: check the **safety gate**, run the tool,
     append the result, and loop so the model can use the output.
6. **Safety gate** (`agent._check_gate`): risky shell commands and *all* emails pause
   and return `needs_confirmation`. The human answers; the frontend re-posts with
   `confirm=true/false`.
7. **Reflection:** every `REFLECT_EVERY_N_TURNS` assistant turns, `reflect_and_remember`
   reviews recent history and saves durable notes.

## Why it's split this way

- **The brain has no web dependency.** `agent.py` and everything under `core/` and
  `tools/` are plain Python. `cli.py` drives them directly; `ui_server.py` is just an
  HTTP adapter. You can embed the brain in anything.
- **Tools are data + functions.** Adding a capability never touches `agent.py` — see
  [tools.md](tools.md).
- **Models are swappable roles.** Change a role → model mapping in `config.py`; nothing
  else needs to know.

## State & storage

Everything Sakura AI remembers lives under `~/.jarvis/` (override with `JARVIS_DATA`):

| File | Contents |
|---|---|
| `memory.sqlite3` | `messages` (rolling transcript) + `notes` (durable facts) |
| `knowledge.sqlite3` | RAG `chunks` (text + embedding vector as JSON) |
| `transcripts/` | reserved for good runs you may later fine-tune on (see roadmap) |
| `last_screenshot.png` | most recent screen capture for the vision model |
