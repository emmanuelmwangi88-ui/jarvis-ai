# Project structure

Sakura AI is a small, layered codebase: a browser UI talks to a FastAPI backend, which
drives a local Ollama model through an agent loop with tools, memory, and RAG.

```
jarvis/
├── launch.py              # one-command entry point (starts Ollama + backend + window)
├── cli.py                 # headless terminal chat (no browser)
├── requirements.txt
├── README.md
│
├── core/                  # the brain — pure Python, no web framework
│   ├── config.py          # ALL settings + hardware auto-tuning + system prompt
│   ├── agent.py           # the agent loop: model ↔ tools, streaming, confirm gates
│   ├── model_router.py    # picks which model/role handles a message
│   ├── ollama_check.py    # start/probe Ollama, chat + stream calls, 8GB server env
│   ├── memory.py          # SQLite: history, notes, skills
│   ├── rag.py             # local embeddings knowledge base
│   ├── metrics.py         # CPU / RAM / tokens-per-sec telemetry
│   └── voice.py           # speech-in (faster-whisper) + speech-out
│
├── tools/                 # the hands — what the agent can DO
│   └── tools.py           # file/shell/app/web/email/learn tools + JSON schema
│
├── ui/                    # the face
│   ├── ui_server.py       # FastAPI: pages + /api/* endpoints, serves /static
│   └── static/            # the web app (served at /static, no build step)
│       ├── index.html     # markup only (structure, blossom-tree SVGs, modals)
│       ├── css/
│       │   └── base.css   # layout + components, 100% CSS-variable driven
│       └── js/
│           ├── themes.js      # theme palettes + settings/theme modal
│           ├── background.js  # falling-petal canvas engine (theme-aware)
│           └── app.js         # chat, streaming, tools, voice, palette, wiring
│
└── docs/                  # you are here
```

## Layer boundaries (who imports whom)
- `core/*` imports only other `core/*` (and `config` is the hub everything reads).
- `tools/tools.py` imports `core` (config, memory, rag) — never the UI.
- `ui/ui_server.py` imports `core` + `tools` and exposes them over HTTP.
- The browser (`static/*`) only talks to the backend over `/api/*` — never imports Python.

This keeps the agent brain testable without a server, and the UI swappable without
touching the brain.

## Frontend module split
The web app used to be one large `index.html`. It is now three focused JS modules plus
one stylesheet, served statically by FastAPI:
- **themes.js** owns look-and-feel: the theme palettes, the settings modal, and
  persistence (localStorage). Selecting a theme rewrites CSS variables live.
- **background.js** owns the animated petals; it listens for theme changes and recolors.
- **app.js** owns behavior: chat streaming, tool/activity rendering, voice, autonomy &
  performance controls, and the command palette.

> Note: because the modules load from `/static/...`, the full experience needs the app
> served by `ui_server.py` (or `launch.py`). Opening `index.html` from disk without the
> server won't load the CSS/JS.
