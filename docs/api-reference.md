# API Reference

Base URL: `http://127.0.0.1:8765` (host/port from `core/config.py` → `ServerConfig`).
All bodies are JSON unless noted. Local-only by default.

---

## `GET /`
Serves the chat UI (`ui/static/index.html`).

---

## `GET /api/status`
Connection + readiness snapshot. Polled by the UI.

**Response**
```json
{
  "connected": true,
  "host": "http://127.0.0.1:11434",
  "installed": ["llama3.2:1b", "qwen2.5-coder:3b", "..."],
  "required":  ["llama3.2:1b", "llama3.2:latest", "qwen2.5-coder:3b",
                "gemma3:4b", "moondream:1.8b", "nomic-embed-text"],
  "missing":   [],
  "ready":     true,
  "rag":       { "chunks": 42, "documents": 3 },
  "autonomy":  "safe",
  "workspace_lock": null,
  "poll_seconds": 15
}
```

---

## `POST /api/chat`
Send a message. Re-send with `confirm` to resolve a pending gated action.

**Request**
```json
{ "text": "list the files in my Downloads folder", "confirm": null }
```
| Field | Type | Notes |
|---|---|---|
| `text` | string | the user message (re-send the *same* text when confirming) |
| `confirm` | bool \| null | `true`/`false` to resolve a pending confirmation; `null` otherwise |

**Response**
```json
{
  "reply": "Here are the files…",
  "role": "tools",
  "model": "qwen2.5-coder:3b",
  "tool_calls": [
    { "name": "list_dir", "args": {"path": "~/Downloads"}, "result": "…" }
  ],
  "needs_confirmation": null
}
```

When a risky command or an email needs approval:
```json
{
  "reply": "This command looks risky: …  Confirm to run it.",
  "needs_confirmation": {
    "action": "run_command",
    "args": { "command": "rm -rf ./build", "confirmed": false },
    "review": "This deletes the build directory recursively; data loss if wrong path.",
    "message": "This command looks risky:\n\n    rm -rf ./build\n\n…Confirm to run it."
  }
}
```
The client shows the card, then POSTs again with the same `text` and `confirm:true|false`.

---

## `POST /api/chat/stream`
Streaming chat via **Server-Sent Events** — tokens arrive as they generate (the fast,
ChatGPT-style feel). Same request body as `/api/chat`.

Each SSE line is `data: {json}`. Event shapes:
```jsonc
{"t":"route","role":"chat","model":"llama3.2:latest"}
{"t":"token","d":"partial text "}          // many of these
{"t":"tool","name":"web_search","args":{...},"result":"..."}
{"t":"confirm","info":{...}}                // pause for authorization
{"t":"done","role":"...","model":"...","reply":"full text","tool_calls":[...]}
{"t":"error","message":"..."}
{"t":"end"}                                  // always last
```
On a `confirm` event the client re-POSTs the same `text` with `confirm:true|false`.

---

## `POST /api/autonomy`
Switch the autonomy profile.
```jsonc
{ "profile": "trusted" }   // one of: locked | trusted | unleashed
// -> { "profile":"trusted", "autonomy":"safe", "runtime":{...} }
```
| Profile | Effect |
|---|---|
| `locked` | shell + file writes OFF; read/web only |
| `trusted` | full capability; only destructive shell commands confirm (default) |
| `unleashed` | `AUTONOMY=yolo` — nothing gated except email |

---

## `GET /api/learning`
Self-learning snapshot for the UI panel.
```json
{ "skills": [ {"name":"deploy site","content":"...","uses":3} ],
  "notes": ["User prefers concise answers", "..."], "skill_count": 5 }
```

---

## `POST /api/voice`
Multipart form: a recorded audio clip → transcript + reply + spoken audio.

**Request** (`multipart/form-data`)
| Field | Type | Notes |
|---|---|---|
| `audio` | file | recorded clip (e.g. `audio/webm`) |
| `confirm` | string | `""`, `"true"`, or `"false"` |

**Response**
```json
{
  "transcript": "what's on my screen",
  "reply": "Looks like your code editor with…",
  "audio_b64": "<base64 WAV, empty if TTS unavailable>",
  "role": "vision",
  "model": "moondream:1.8b",
  "tool_calls": [ { "name": "screenshot", "result": "/…/last_screenshot.png" } ],
  "needs_confirmation": null
}
```

---

## `POST /api/reflect`
Force a reflect-and-remember pass now.
```json
{ "result": "Reflected and saved 2 note(s)." }
```

---

## `POST /api/reset`
Clear the conversation history (notes and RAG are kept).
```json
{ "result": "Conversation history cleared." }
```

---

## `GET /api/metrics`
Live system telemetry for the dashboard cards. Polled every ~8s by the UI.
```json
{
  "cpu_percent": 42.4, "cpu_cores": 8, "cpu_per_core": [ ... ],
  "mem_used_gb": 8.42, "mem_total_gb": 16.0, "mem_percent": 53.0,
  "temp_c": 48.2,                 // null if no sensor is available
  "tokens_per_sec": 132.8,        // from the last generation
  "ttft_ms": 7.2, "pid": 41902, "connected": true
}
```

---

## `GET /api/settings` · `POST /api/settings`
Read or flip the **Agent Sandbox** toggles. These are enforced live by the tools layer.
```jsonc
// GET
{ "runtime": {"shell": true, "fs_write": true, "web": true, "audio": true},
  "autonomy": "safe" }

// POST body — key is one of shell|fs_write|web|audio|yolo
{ "key": "web", "value": false }   // disables web_search / fetch_url / open_url
```

---

## `POST /api/unload`
Flush all loaded models out of RAM/VRAM ("Flush VRAM Cache").
```json
{ "ok": true, "message": "Model cache flushed." }
```

---

## `POST /api/benchmark`
Time a tiny generation on the primary model ("Run System Benchmark").
```json
{ "ok": true, "elapsed_ms": 190, "tokens_per_sec": 132.8,
  "ttft_ms": 7.2, "model": "llama3.2:latest", "message": "…" }
```

---

## `GET /api/history?limit=200`
Full recent transcript for "Export Session Logs".
```json
{ "messages": [ {"role": "user", "content": "…"}, {"role": "assistant", "content": "…"} ] }
```

---

## Error shape
Tool-level failures are returned *inside* `reply`/`tool_calls` as strings beginning with
`ERROR:` — the agent keeps running. Transport failures (e.g. voice deps missing) return a
non-200 with `{ "error": "…" }`.
