# Performance & speed (tuned for 8GB RAM)

On a laptop with 8GB RAM the single biggest cost isn't inference — it's **model
swapping**. Every time the router picks a different model, Ollama unloads the old one and
loads the new one from disk (several seconds). Sakura AI is tuned to avoid that.

## What makes it fast

### 1. Keep one model hot (`keep_alive`)
Every Ollama call sends `keep_alive` (default `8m`, `config.KEEP_ALIVE`). The model
stays resident in RAM between messages, so the *next* reply starts instantly instead of
reloading — but it's short enough that an idle session frees the RAM again on 8GB. The
backend also **preloads** the primary model on startup (`ollama_check.preload()`), so
even your first message is fast.

### 2. Single-model mode (`SINGLE_MODEL_MODE`, on by default)
Chat, reasoning, and general tool turns all use one **primary** model
(`llama3.2:latest`, the 3B) instead of hopping between three models. You keep ONE model
hot the whole session. Exceptions that are worth a swap:
- **explicit code tasks** → `qwen2.5-coder:3b`
- **screen questions** → `moondream:1.8b`
- **trivial greetings** → `llama3.2:1b` (tiny, instant)

Turn it off for maximum per-task quality (at the cost of reloads):
```bash
SAKURA_SINGLE_MODEL=0 python launch.py
```

### 3. Capped generation (`GEN_OPTIONS`)
| Option | Default | Why |
|---|---|---|
| `num_ctx` | 3072 | smaller context = less RAM + faster prompt eval |
| `num_predict` | 900 | stops a small model from rambling for 30s |
| `num_thread` | all cores | use the whole CPU |
| `temperature` | 0.6 | focused, less meandering |

Override any of them with env vars: `SAKURA_NUM_CTX`, `SAKURA_NUM_PREDICT`,
`SAKURA_NUM_THREAD`.

### 4. Shorter history window (`HISTORY_LIMIT`, default 8)
Only the last 8 messages are fed back as context. Less text to process each turn = faster,
and the durable **notes** (from `remember()`/reflection) preserve the important stuff
anyway. Raise it with `SAKURA_HISTORY` if you want longer memory per turn.

### 5. Cheap safety review
The risky-command "second opinion" uses the tiny `llama3.2:1b` with a 160-token cap — a
fast gut-check instead of loading a bigger model at the confirmation gate.

### 6. Background self-reflection on the primary model (8GB-safe)
Self-reflection used to load `gemma3:4b` (~3.3GB) *on top of* the hot 3B primary — on an
8GB laptop that exhausted RAM and **hung the machine**. It now (a) reuses the already-hot
**primary** model with a 200-token cap, and (b) runs in a **background daemon thread**, so
it never blocks your reply and never loads a second large model. It also runs less often
(`SAKURA_REFLECT_EVERY`, default every 5 turns). Speech-in uses the lightweight
`tiny.en` Whisper model for the same reason.

## Speed vs. quality dial

| Goal | Setting |
|---|---|
| **Fastest** | `SINGLE_MODEL_MODE=1`, `num_ctx=2048`, `num_predict=512` |
| **Balanced (default)** | `SINGLE_MODEL_MODE=1`, `num_ctx=3072`, `num_predict=900` |
| **Best answers** | `SAKURA_SINGLE_MODEL=0` (routes to `gemma3:4b`/`qwen2.5-coder` per task) |

## If replies are still slow
1. Close other apps — 8GB fills quickly and swapping to disk kills speed.
2. Keep `SINGLE_MODEL_MODE` on so you're not reloading models.
3. Lower `SAKURA_NUM_CTX` to 2048.
4. Make the router prefer `llama3.2:1b` more often (edit `_TRIVIAL_CHARS` /
   thresholds in `model_router.py`).
5. Confirm nothing else is hammering the CPU while a model runs.
