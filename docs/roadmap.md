# Roadmap — "make it better than Claude"

Let's be straight, because it matters for what you build next.

## The honest baseline
A 1B–4B model running on 8GB of RAM **will not out-reason, out-code, or out-write
Claude/GPT-4-class models.** Those models are hundreds of billions of parameters trained
on clusters you can't fit in a laptop. No amount of prompting or local fine-tuning closes
that raw-capability gap. Anyone who tells you otherwise is selling something.

**But "better" isn't one axis.** On the axes that actually matter for a *personal*
assistant, a local agent can genuinely beat a cloud chatbot:

| Axis | Cloud Claude | Sakura AI (local) |
|---|---|---|
| Raw reasoning / coding quality | 🏆 far ahead | behind |
| Acts on *your* machine (files, shell, apps) | ✗ can't | 🏆 yes |
| Privacy (nothing leaves the device) | ✗ | 🏆 yes |
| Always available, no account/quota/cost | ✗ | 🏆 yes |
| Persistent memory of *you* across sessions | limited | 🏆 yes, local |
| Latency for small tasks | network round-trip | 🏆 local |

Sakura AI is already "better" on the right-hand rows. This roadmap pushes the quality gap
as far as it can realistically go.

## Tier 1 — squeeze the local models (free, do these first)
1. **Right-size the router.** Send more hard prompts to `gemma3:4b` (turn off single-model
   mode); keep `llama3.2:1b` for trivia. Tune keywords + `_LONG_MESSAGE_CHARS` in
   `model_router.py`.
2. **Bigger models if RAM allows.** Swap roles in `config.MODELS` to 7B/8B quantized
   (`qwen2.5:7b`, `llama3.1:8b`) — a large quality jump if you can spare the memory.
3. **Better retrieval.** Feed the model *your* docs via `remember_document()` so answers
   are grounded in your files instead of the model's thin parametric memory.
4. **Structured prompting.** Add a "think step by step, then answer" scaffold for the
   `reason` role; it meaningfully helps small models.

## Tier 2 — hybrid: local by default, big brain on demand
The pragmatic way to actually approach "better than Claude" without giving up privacy for
routine work:

- Add a `cloud` role in `config.MODELS` and a `call_cloud()` in `ollama_check.py` (or a
  new `cloud.py`) that hits an API (Claude, GPT, Gemini, …) **only** for prompts you flag
  as hard.
- Route to it explicitly (a `/hard` prefix, a UI toggle, or a difficulty heuristic).
- Keep every system-touching tool local. You get frontier reasoning *when you ask for it*
  and full local privacy for everything else.

> You chose "best possible local agent," so this stays optional — but it's the honest
> answer to the literal request, and the wiring is one module.

## Tier 3 — real learning (a separate, manual project)
The README's `reflect_and_remember()` is **accumulated context, not weight updates.**
Actual weight-level personalization looks like:
1. Log good transcripts (the `transcripts/` dir is reserved for this).
2. Periodically LoRA-fine-tune a base model on them using a free Colab/Kaggle GPU.
3. Convert the adapter to GGUF and load it back into Ollama as a custom model.

This is a deliberate, offline pipeline — not something running live on the laptop. It
personalizes *style and recall*, not raw intelligence.

## What NOT to expect
- Live self-modification / self-retraining on this hardware. Doesn't happen.
- A 3B model matching Claude on a hard algorithm design or a long nuanced essay.
- "AGI in a box." This is a sharp, private, tool-using assistant for *your* machine —
  which, for day-to-day personal use, is often the more useful thing to have.
