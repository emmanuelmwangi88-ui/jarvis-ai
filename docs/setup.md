# Setup

## 1. Install Ollama

Download from <https://ollama.com>. You don't need to start it by hand —
`launch.py` connects to it and runs `ollama serve` for you if it isn't already up.

## 2. Pull the models

```bash
ollama pull llama3.2           # 3B primary brain (llama3.2:latest) — good + fast
ollama pull llama3.2:1b        # tiny/fast: greetings + risky-command review
ollama pull qwen2.5-coder:3b   # explicit code tasks
ollama pull gemma3:4b          # reasoning / long-form (multi-model mode)
ollama pull moondream:1.8b     # vision (screen questions)
ollama pull nomic-embed-text   # RAG embeddings
```

> `qwen3:4b` and `phi3.5:3.8b` from earlier drafts are no longer required — the config
> now uses `llama3.2:latest` (primary), `gemma3:4b` (reasoning), and `llama3.2:1b`
> (review). Keeping the old models installed does no harm.

The status indicator in the UI turns **amber** and lists exactly which of these are
missing, so you always know what's left to pull.

## 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

Voice (`faster-whisper`, `piper-tts`) and OCR (`pytesseract`) are optional — the app
runs without them; those specific features just report a friendly error if used.

## 4. (Optional) Email

Edit `core/config.py` → `EmailConfig`, or set environment variables:

```bash
export JARVIS_EMAIL="you@gmail.com"
export JARVIS_EMAIL_PASSWORD="your-app-password"   # https://myaccount.google.com/apppasswords
```

## 5. (Optional) OCR

Install the Tesseract binary — <https://github.com/UB-Mannheim/tesseract/wiki>.
`pytesseract` just wraps it.

## 6. Run it

```bash
python launch.py     # fullscreen window (pywebview), or browser fallback
python cli.py        # terminal-only, no UI
```

First voice reply is slow — Piper downloads its voice and faster-whisper downloads its
model on first use, then both are cached.

## Configuration knobs (env vars)

Every variable below can use the **`SAKURA_`** prefix; the legacy **`JARVIS_`**
prefix still works as a fallback, so old shell profiles keep running.

| Variable | Default | Effect |
|---|---|---|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Where Ollama listens |
| `SAKURA_AUTONOMY` | `safe` | `safe` gates risky commands + deletes; `yolo` skips those gates (email still confirms) |
| `SAKURA_WORKSPACE` | *(unset)* | Restrict file tools to this folder tree |
| `SAKURA_DATA` | `~/.jarvis` | Where the DB, RAG index, transcripts live |
| `SAKURA_EMAIL` / `SAKURA_EMAIL_PASSWORD` | *(unset)* | Enable `send_email` |
| `SAKURA_SINGLE_MODEL` | `1` | `1` keeps one model hot (fast on 8GB); `0` routes per-task for max quality |
| `SAKURA_KEEP_ALIVE` | `8m` | How long Ollama keeps a model resident between messages |
| `SAKURA_NUM_CTX` | `3072` | Context window (smaller = faster, less RAM) |
| `SAKURA_NUM_PREDICT` | `900` | Max reply length |
| `SAKURA_REFLECT_EVERY` | `5` | Self-reflection runs every N turns (background, primary model) |
| `SAKURA_HISTORY` | `8` | Past messages fed back as context |

See [performance.md](performance.md) for the full speed/quality dial.

## Troubleshooting

- **Status dot is red / "Ollama offline".** Ollama isn't running or `OLLAMA_HOST` is
  wrong. Run `ollama serve` manually and reload.
- **Status dot is amber.** Some models aren't pulled — the text names how many; pull them.
- **Replies are slow.** 8GB RAM is tight. Close other apps, or make `model_router.py`
  fall back to `llama3.2:1b` more aggressively.
- **`python launch.py` opens a browser instead of a window.** `pywebview` isn't
  installed: `pip install pywebview`.
- **Voice does nothing.** Install `faster-whisper` and either the `piper` CLI or
  `piper-tts`. Check the browser granted mic permission.
