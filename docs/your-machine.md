# Tuning for your machine (AMD Ryzen 5 5650U · 8 GB)

Sakura auto-detects your hardware at startup and picks a profile. This page explains
what it chose and how to squeeze more out of this specific laptop.

## What Sakura detected
| Signal | Your machine | What it means |
|---|---|---|
| RAM | 8 GB DDR4 3200 (**single stick = single-channel**) | Tight, and ~half the memory bandwidth of a dual-stick setup |
| Hardware-reserved | 1.2 GB | ~6.8 GB actually usable by apps + models |
| Free at idle | **~0.6 GB** | Windows + apps already fill RAM; big models would page to disk |
| CPU | Ryzen 5 5650U, **6 cores / 12 threads** | Good for CPU inference |
| GPU | Radeon (Vega) integrated | **Not usable by Ollama on Windows** — no ROCm for Vega iGPUs → CPU inference |

Because total RAM ≤ 9 GB, Sakura turns on **Low-RAM Mode** automatically:

| Setting | Value | Why |
|---|---|---|
| Primary model | `llama3.2:1b` (~1.3 GB) | Fits in free RAM without paging; stays hot |
| `num_ctx` | 2048 | Smaller KV-cache = less RAM, faster prompt eval |
| `num_predict` | 640 | Keeps replies snappy |
| `num_thread` | 6 (physical cores) | Physical cores beat logical/SMT for llama.cpp |
| `keep_alive` | 4m | Frees the model from RAM when you stop using it |
| Single-model mode | forced ON | No mid-session model swaps (a swap briefly needs 2 models = the old hang) |
| Background reflection | skipped when free RAM < 1.2 GB | Never tips you into a freeze |

You can see the live profile in the **Live Telemetry** panel ("Low-RAM profile").

## The single biggest upgrade: a second RAM stick
You have **1 of 2 SODIMM slots used**. Adding a matching 8 GB DDR4-3200 SODIMM does two
things at once:
1. **16 GB total** — comfortably run the 3B/4B models with headroom.
2. **Dual-channel** — roughly *doubles* memory bandwidth, and token generation on a CPU
   is bandwidth-bound, so you'd get a real speed jump even at the same model size.

This is a bigger win than any software setting. ~$20–30 part.

## Getting more quality *without* new hardware
- **Close Chrome/Teams before a heavy task.** Freeing 1–2 GB lets you step up a model.
- **Step up to the 3B brain when you have headroom:**
  ```bat
  set SAKURA_PRIMARY_MODEL=llama3.2:latest
  set SAKURA_NUM_CTX=3072
  ```
- **Best answers, accept reloads** (routes to `qwen2.5-coder:3b` / `gemma3:4b` per task):
  ```bat
  set SAKURA_SINGLE_MODEL=0
  ```
- **Force the low-RAM profile off/on** regardless of detection:
  ```bat
  set SAKURA_LOW_RAM=0   REM or 1
  ```

## Fastest-possible (if 1b still feels heavy)
```bat
set SAKURA_PRIMARY_MODEL=qwen2.5:0.5b   REM if pulled; ~0.4GB, very fast, weaker
set SAKURA_NUM_CTX=1536
set SAKURA_NUM_PREDICT=512
```

## Built-in performance layer (automatic)
Sakura now tunes the **Ollama server itself** when it launches it — these matter far
more than per-request settings on 8 GB:

| Ollama env (auto-set) | Value | Effect |
|---|---|---|
| `OLLAMA_MAX_LOADED_MODELS` | 1 | Never keeps two models in RAM at once — kills the hang at the source |
| `OLLAMA_NUM_PARALLEL` | 1 | One request at a time → far less KV-cache RAM reserved |
| `OLLAMA_FLASH_ATTENTION` | 1 | ~20–30% faster context handling, less memory |
| `OLLAMA_KV_CACHE_TYPE` | q8_0 | Quantizes the KV cache — roughly halves its RAM |
| `OLLAMA_KEEP_ALIVE` | 4m | Idle sessions release the model |

> If Ollama is *already running* when you start Sakura, it prints the exact `setx`
> commands to apply these yourself (they only take effect on a server Sakura launches).

## Live Performance switch (in the UI)
The AI-Core panel has a **Performance** control:
- **Fast** — `llama3.2:1b`, snappiest, lightest on RAM (default on your laptop).
- **Balanced** — the 3B brain for better answers; use it after closing some apps.
- **Quality** — routes to specialist models per task (best answers, reloads between tasks).

And a **"Try iGPU offload (Vulkan)"** checkbox that sets GPU layers + flips
`OLLAMA_VULKAN=1`. Restart Ollama for it to engage the Vega iGPU. Expect a modest
effect at best — the iGPU shares your system RAM — so benchmark Fast-CPU vs GPU and keep
whichever is quicker.

## Rule of thumb for this laptop
Keep **one** small model hot, keep context small, and add the second RAM stick when you
can. Everything else (streaming, tools, self-learning) already works within these limits.
