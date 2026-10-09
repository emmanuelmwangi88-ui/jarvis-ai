# Backend

The backend is two things: a thin **HTTP layer** (`ui/ui_server.py`, FastAPI) and the
**brain** it wraps (`core/`). The CLI (`cli.py`) skips the HTTP layer and drives the
brain directly — so the brain is the real backend; FastAPI is just one adapter.

## HTTP layer — `ui/ui_server.py`

A small FastAPI app. On startup it ensures data dirs exist and initializes the SQLite
schemas. Endpoints are documented in [api-reference.md](api-reference.md). It binds to
`127.0.0.1` by design (local-only). Static assets are mounted at `/static`.

## The brain — `core/agent.py`

`handle_message(user_text, confirm=None, on_event=None) -> AgentResult` is the whole
public surface. `AgentResult` carries the `reply`, which `role`/`model` handled it, the
`tool_calls` that ran, and an optional `needs_confirmation` payload.

The loop:

```
route(text) → role, model, wants_tools
if role == vision:  screenshot → vision model → return       # bypasses tools
messages = system + notes + recent history + text
repeat up to MAX_TOOL_ITERATIONS:
    msg = ollama.chat(model, messages, tools)
    if no tool_calls: return msg.content                     # done
    for call in msg.tool_calls:
        gate = check_gate(call, confirm)
        if gate: return needs_confirmation                   # pause for human
        result = run_tool(call)                              # execute
        append result to messages
```

`on_event(kind, data)` is an optional callback the CLI uses to print live status
(`route`, `thinking`, `tool`, `reflect`). The HTTP layer ignores it.

## Model access — `core/ollama_check.py`

- `is_up()` / `start_server()` — detect and auto-launch `ollama serve`.
- `installed_models()` / `missing_models()` / `status()` — power the UI indicator.
- `chat(model, messages, tools, images, options)` — POST `/api/chat` (non-streaming);
  returns the `message` dict (which may hold `content` and/or `tool_calls`).
- `embed(model, text)` — POST `/api/embeddings`; returns the vector for RAG.

All failures raise `OllamaError`, which the agent catches and turns into a plain-language
reply instead of a stack trace.

Every call automatically applies `config.GEN_OPTIONS` (context/length/thread caps) and
`config.KEEP_ALIVE` so models stay hot in RAM between messages. `preload()` warms the
primary model on startup. See [performance.md](performance.md) for the full tuning story.

## Routing — `core/model_router.py`

Pure keyword + length heuristics, no ML, fully transparent. Returns
`(role, model, wants_tools)`. See the table in the main [README](../README.md#model-routing).
Edit the keyword sets or `_LONG_MESSAGE_CHARS` to retune.

## Memory — `core/memory.py`

SQLite with two tables: `messages` (rolling transcript, fed back as context) and `notes`
(durable facts saved by `remember()` / reflection). `notes_as_context()` renders notes
into the system prompt so lessons persist across sessions.

## RAG — `core/rag.py`

`remember_document(path)` chunks a text file (900 chars, 150 overlap), embeds each chunk
with `nomic-embed-text`, and stores it. `search_knowledge(query)` embeds the query and
ranks chunks by cosine similarity in Python — no vector DB dependency, fine for a
personal-scale corpus.

## Voice — `core/voice.py`

`transcribe(bytes)` uses faster-whisper (CPU, int8); `synthesize(text)` uses Piper (CLI
preferred, python package fallback). Both imports are lazy, so a missing voice dependency
never blocks text chat.

## Self-improvement — `reflect_and_remember()`

Runs automatically every `REFLECT_EVERY_N_TURNS` assistant turns (and on CLI exit). It
asks the reasoning model to extract up to 3 durable lessons from recent history and saves
them as notes. This is **accumulated context, not weight-level learning** — see
[roadmap.md](roadmap.md) for the real fine-tuning path.

## Extending the backend
- **New capability:** add a function + schema + registry entry in `tools/tools.py`.
  Nothing in `agent.py` changes.
- **New model role:** add it to `config.MODELS` and teach `model_router.route` when to
  pick it.
- **New endpoint:** add a route in `ui_server.py` that calls into `core/`.
