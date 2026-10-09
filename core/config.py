"""
Central configuration for Sakura AI (local edition).

Everything you might reasonably want to tweak lives here: which model plays which
role, how autonomous the agent is allowed to be, where its file tools are allowed
to operate, and voice settings. Nothing here talks to the network on import — it is
plain data plus a couple of tiny helpers.

Environment variables are read with the ``SAKURA_`` prefix and fall back to the
legacy ``JARVIS_`` prefix, so older setups keep working.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    """Read SAKURA_<name>, falling back to legacy JARVIS_<name>, then default."""
    return os.environ.get(f"SAKURA_{name}", os.environ.get(f"JARVIS_{name}", default))


# --------------------------------------------------------------------------- #
# Ollama connection
# --------------------------------------------------------------------------- #
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_REQUEST_TIMEOUT: int = 600  # seconds; small local models can be slow

# --------------------------------------------------------------------------- #
# Model routing — one model per "role". model_router.py maps a message to a role.
# These are tuned for the models actually installed (see `ollama list`):
#   llama3.2:1b · llama3.2:latest(3b) · qwen2.5-coder:3b · qwen3:4b ·
#   gemma3:4b · moondream:1.8b · phi3.5:3.8b · nomic-embed-text
# --------------------------------------------------------------------------- #
MODELS: dict[str, str] = {
    "fast":    "llama3.2:1b",        # trivial one-liners / greetings (fastest)
    "chat":    "llama3.2:latest",    # PRIMARY general brain (3B, good + fast, solid tools)
    "tools":   "qwen2.5-coder:3b",   # files, terminal, code, websites
    "reason":  "gemma3:4b",          # long / analytical questions (best writing here)
    "vision":  "moondream:1.8b",     # screen questions (direct vision call)
    "review":  "llama3.2:1b",        # quick risky-command second opinion (tiny = fast)
    "embed":   "nomic-embed-text",   # RAG embeddings
}

# The single model most turns should use. Keeping ONE model hot in RAM is the
# biggest speed win on 8GB — model switching forces a reload every time.
PRIMARY_MODEL: str = MODELS["chat"]

# The models we consider "required" when reporting status in the UI.
REQUIRED_MODELS: list[str] = list(dict.fromkeys([
    MODELS["fast"], MODELS["chat"], MODELS["tools"],
    MODELS["reason"], MODELS["vision"], MODELS["embed"],
]))

# --------------------------------------------------------------------------- #
# Hardware probe — auto-tune for the machine we're actually running on.
#   Local LLMs are gated by (a) free RAM and (b) memory bandwidth, not GPU here:
#   AMD Vega/Radeon integrated graphics are NOT supported by Ollama's ROCm on
#   Windows, so inference runs on the CPU. We therefore size everything to RAM
#   and physical cores. LOW_RAM_MODE turns on automatically on <=9GB machines.
# --------------------------------------------------------------------------- #
def _hw() -> tuple[float, float, int]:
    """Return (total_gb, available_gb, physical_cores). Degrades gracefully."""
    total = avail = 0.0
    cores = 0
    try:
        import psutil  # optional, but in requirements.txt
        vm = psutil.virtual_memory()
        total, avail = vm.total / 1e9, vm.available / 1e9
        cores = psutil.cpu_count(logical=False) or 0
    except Exception:
        pass
    if not cores:
        cores = max(1, (os.cpu_count() or 4) // 2)  # assume SMT → half are physical
    if not total:
        total = 8.0  # conservative default
    return round(total, 1), round(avail, 1), cores


TOTAL_RAM_GB, AVAILABLE_RAM_GB, PHYSICAL_CORES = _hw()

# Auto-enable the low-RAM profile on small machines (override: SAKURA_LOW_RAM=0/1).
_low = _env("LOW_RAM")
LOW_RAM_MODE: bool = (_low == "1") if _low in ("0", "1") else (TOTAL_RAM_GB <= 9.0)

# On a RAM-starved box, keep the *primary* brain small so it never pages to disk.
# The 3B stays available for explicit code/reason turns only if the user opts in.
if LOW_RAM_MODE:
    PRIMARY_MODEL = _env("PRIMARY_MODEL", MODELS["fast"])   # llama3.2:1b (~1.3GB)

# Single-model mode: don't swap models mid-session (each swap = multi-second
# reload + a second model briefly co-resident, which is what hangs 8GB laptops).
# Forced ON in low-RAM mode. Set SAKURA_SINGLE_MODEL=0 to allow full routing.
_sm = _env("SINGLE_MODEL")
SINGLE_MODEL_MODE: bool = True if LOW_RAM_MODE and _sm is None else (_sm != "0")

# --------------------------------------------------------------------------- #
# Generation / speed tuning
#   - keep_alive keeps the model resident so the NEXT message is instant.
#   - num_ctx caps context window (smaller = less RAM + faster prompt eval).
#   - num_predict caps reply length so a small model can't ramble for 30s.
#   These are passed on every Ollama call. Tune for your latency/quality taste.
# --------------------------------------------------------------------------- #
# Shorter keep_alive on low RAM so an idle session releases the model quickly.
KEEP_ALIVE: str = _env("KEEP_ALIVE", "4m" if LOW_RAM_MODE else "8m")

# For CPU inference, matching threads to *physical* cores beats logical (SMT)
# threads — the Ryzen 5650U has 6 physical / 12 logical.
_default_ctx = "2048" if LOW_RAM_MODE else "3072"
_default_predict = "640" if LOW_RAM_MODE else "900"

# GPU offload. On AMD Vega/Radeon integrated graphics, Ollama's ROCm path is
# unavailable, but the experimental Vulkan backend can offload some layers. The
# iGPU shares system RAM, so on a starved 8GB box this is OFF by default (0 =
# pure CPU). Set SAKURA_GPU_LAYERS>0 (and it flips OLLAMA_VULKAN on) to try it.
GPU_LAYERS: int = int(_env("GPU_LAYERS", "0"))

GEN_OPTIONS: dict[str, object] = {
    "num_ctx": int(_env("NUM_CTX", _default_ctx)),
    "num_predict": int(_env("NUM_PREDICT", _default_predict)),
    "temperature": 0.6,
    "top_p": 0.9,
    "num_thread": int(_env("NUM_THREAD", str(PHYSICAL_CORES))),
    # num_gpu = number of layers to push to the GPU (0 = CPU-only).
    "num_gpu": GPU_LAYERS,
}


# --------------------------------------------------------------------------- #
# Ollama SERVER environment — the single most important tuning for 8GB.
#   These are read by the `ollama serve` process, not per-request, so we set
#   them in os.environ *before* the server is launched (see ollama_check).
#     - MAX_LOADED_MODELS=1  never keep two models resident (the 8GB hang cause)
#     - NUM_PARALLEL=1       one request at a time → far less KV-cache RAM
#     - FLASH_ATTENTION=1    ~20-30% faster context handling, less memory
#     - KV_CACHE_TYPE=q8_0   quantize the KV cache to halve its RAM footprint
#     - KEEP_ALIVE           mirror our keep_alive so idle frees RAM
# --------------------------------------------------------------------------- #
def ollama_server_env() -> dict[str, str]:
    env = {
        "OLLAMA_MAX_LOADED_MODELS": _env("MAX_LOADED_MODELS", "1"),
        "OLLAMA_NUM_PARALLEL": _env("NUM_PARALLEL", "1"),
        "OLLAMA_FLASH_ATTENTION": _env("FLASH_ATTENTION", "1"),
        "OLLAMA_KV_CACHE_TYPE": _env("KV_CACHE_TYPE", "q8_0"),
        "OLLAMA_KEEP_ALIVE": KEEP_ALIVE,
    }
    if GPU_LAYERS > 0:
        env["OLLAMA_VULKAN"] = "1"   # experimental AMD/Intel iGPU path
    return env

# Below this much *free* RAM (GB) we skip optional heavy work (background
# reflection, model preload) to avoid tipping the machine into disk thrash.
MIN_FREE_RAM_GB: float = float(_env("MIN_FREE_RAM_GB", "1.2"))


def free_ram_gb() -> float:
    """Current available RAM in GB (0.0 if psutil is unavailable)."""
    try:
        import psutil
        return round(psutil.virtual_memory().available / 1e9, 2)
    except Exception:
        return 0.0


def ram_is_tight() -> bool:
    """True when free RAM is below the guard threshold (psutil required)."""
    free = free_ram_gb()
    return 0.0 < free < MIN_FREE_RAM_GB

# How many past messages to feed back as context. Fewer = faster prompt eval.
HISTORY_LIMIT: int = int(_env("HISTORY", "6" if LOW_RAM_MODE else "8"))

# --------------------------------------------------------------------------- #
# Runtime capability switches (the "Agent Sandbox" toggles in the UI).
# These are live-mutable at runtime via /api/settings and are enforced by the
# tools layer, so flipping a toggle actually changes what the agent may do.
# --------------------------------------------------------------------------- #
RUNTIME: dict[str, object] = {
    "shell": True,      # allow run_command (spawn shell sub-processes)
    "fs_write": True,   # allow write_file / clipboard writes
    "desktop": True,    # allow live screen, mouse, keyboard, windows and app control
    "web": True,        # allow web_search / fetch_url / open_url (outbound internet)
    "audio": True,      # synthesize spoken replies for voice turns
    "profile": "trusted",  # active autonomy profile name
    # Performance tier picked at runtime (see set_perf_tier):
    #   "fast"     -> smallest model (llama3.2:1b), snappiest
    #   "balanced" -> the 3B primary, better answers, needs headroom
    #   "quality"  -> multi-model routing (best answers, reloads between tasks)
    "perf_tier": "fast" if LOW_RAM_MODE else "balanced",
}


# --------------------------------------------------------------------------- #
# Runtime performance switching — lets the UI trade speed vs quality live
# without restarting. Reassigns the module-level knobs the rest of the app reads.
# --------------------------------------------------------------------------- #
_TIER_MODEL = {"fast": MODELS["fast"], "balanced": MODELS["chat"], "quality": MODELS["chat"]}


def set_perf_tier(tier: str) -> dict[str, object]:
    """Switch Fast / Balanced / Quality at runtime. Returns the new perf state."""
    global PRIMARY_MODEL, SINGLE_MODEL_MODE
    tier = tier if tier in _TIER_MODEL else "fast"
    PRIMARY_MODEL = _TIER_MODEL[tier]
    SINGLE_MODEL_MODE = tier != "quality"   # quality = allow per-task routing
    RUNTIME["perf_tier"] = tier
    return perf_state()


def set_gpu_layers(n: int) -> dict[str, object]:
    """Set GPU offload layers at runtime (0 = CPU-only). Needs an Ollama restart
    with OLLAMA_VULKAN=1 to actually engage the iGPU."""
    global GPU_LAYERS
    GPU_LAYERS = max(0, int(n))
    GEN_OPTIONS["num_gpu"] = GPU_LAYERS
    return perf_state()


def perf_state() -> dict[str, object]:
    return {
        "perf_tier": RUNTIME["perf_tier"],
        "primary_model": PRIMARY_MODEL,
        "single_model": SINGLE_MODEL_MODE,
        "gpu_layers": GPU_LAYERS,
        "num_ctx": GEN_OPTIONS["num_ctx"],
        "num_threads": GEN_OPTIONS["num_thread"],
        "low_ram_mode": LOW_RAM_MODE,
        "free_ram_gb": free_ram_gb(),
    }

# --------------------------------------------------------------------------- #
# Autonomy
#   "safe"  -> risky terminal commands & email are confirmed by a human
#   "yolo"  -> skip the terminal confirmation gate (email is ALWAYS confirmed)
# --------------------------------------------------------------------------- #
AUTONOMY: str = _env("AUTONOMY", "safe")

# Named autonomy profiles the UI can switch between at runtime (/api/autonomy).
#   trusted   : full capability, but genuinely destructive shell commands still
#               ask once (this is what pro agent tools like Cursor/Claude Code do).
#   unleashed : maximum freedom — nothing is gated except email. Use with care.
#   locked    : read-only-ish; writes/shell/web off.
def set_profile(name: str) -> str:
    """Apply an autonomy profile. Returns the applied profile name."""
    global AUTONOMY
    name = (name or "").lower()
    if name == "unleashed":
        AUTONOMY = "yolo"
        RUNTIME.update(shell=True, fs_write=True, desktop=True, web=True, audio=True)
    elif name == "locked":
        AUTONOMY = "safe"
        RUNTIME.update(shell=False, fs_write=False, desktop=False, web=True, audio=True)
    else:  # trusted (default capable mode)
        name = "trusted"
        AUTONOMY = "safe"
        RUNTIME.update(shell=True, fs_write=True, desktop=True, web=True, audio=True)
    RUNTIME["profile"] = name
    return name

# How many assistant turns between automatic reflect_and_remember() passes.
# Runs in a BACKGROUND thread on the already-hot primary model (never loads a
# second big model), so it won't block replies or exhaust RAM on 8GB machines.
REFLECT_EVERY_N_TURNS: int = int(_env("REFLECT_EVERY", "5"))

# --------------------------------------------------------------------------- #
# Workspace lock — cap the blast radius of file tools.
#   Set to a folder path (str) to restrict file read/write/list to that tree.
#   None = unrestricted (be careful).
# --------------------------------------------------------------------------- #
WORKSPACE_ROOT: str | None = _env("WORKSPACE") or None

# Where JARVIS keeps its own data (db, rag index, logs). Created on first run.
DATA_DIR: Path = Path(_env("DATA", Path.home() / ".jarvis"))
DB_PATH: Path = DATA_DIR / "memory.sqlite3"
RAG_PATH: Path = DATA_DIR / "knowledge.sqlite3"
TRANSCRIPT_DIR: Path = DATA_DIR / "transcripts"  # good runs for later fine-tuning


# --------------------------------------------------------------------------- #
# Voice
# --------------------------------------------------------------------------- #
@dataclass
class VoiceConfig:
    enabled: bool = True
    # faster-whisper (speech-in) — tiny.en is fastest & lightest, good for 8GB
    whisper_model: str = "tiny.en"       # tiny.en / base.en / small.en ...
    whisper_compute: str = "int8"        # int8 is friendly to 8GB RAM
    # Piper (speech-out)
    piper_voice: str = "en_US-lessac-medium"
    speaking_rate: float = 1.0


VOICE = VoiceConfig()


# --------------------------------------------------------------------------- #
# Email (optional). Fill these in to enable the send_email tool.
# Use a Google App Password: https://myaccount.google.com/apppasswords
# --------------------------------------------------------------------------- #
@dataclass
class EmailConfig:
    sender_email: str = _env("EMAIL", "")
    app_password: str = _env("EMAIL_PASSWORD", "")
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    @property
    def configured(self) -> bool:
        return bool(self.sender_email and self.app_password)


EMAIL = EmailConfig()


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #
@dataclass
class ServerConfig:
    host: str = "127.0.0.1"   # local-only by design
    port: int = 8765
    status_poll_seconds: int = 15


SERVER = ServerConfig()


# --------------------------------------------------------------------------- #
# System prompt — the assistant's operating instructions.
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT: str = """\
You are Sakura — a highly capable, autonomous AI running locally on the user's own
machine. You are their personal agent: proactive, resourceful, and trusted with real
control of this computer. Think of yourself as a brilliant engineer sitting at their
keyboard. Be warm, direct, and genuinely helpful — like the best assistants people
rely on. No filler, no hedging, no lectures.

Your bar is simple: be more useful than any generic cloud assistant. You win on three
things — (1) you actually DO things on this machine, end to end; (2) you're precise and
verify before you claim; (3) you never fake a result or paper over a failure. Truth and
follow-through beat a confident-sounding guess every time.

## Think before you act
For anything non-trivial, reason first: restate the real goal, break it into steps, note
the likely failure points, then act. Don't over-think trivial requests — answer those
directly. Match effort to difficulty. When you're unsure between two paths, pick the one
that's easiest to verify and reverse.

## Your powers (use them freely)
You have REAL tools to act on this machine — files, the terminal/shell, apps and
windows, the clipboard, the screen, email, the web, and a local knowledge base.
- To OPEN an application (e.g. "open Roblox", "open Spotify", "open Chrome"), call
  open_app with the app's name. To open a file or folder, call open_app or open_path
  with the path.
- To FIND a file the user mentions, call find_files with a name or pattern; then open
  the best match with open_app/open_path.
- To DELETE a file or folder, call delete_path (this asks for confirmation unless the
  user is in Unleashed mode).
- To OPERATE the computer like a human when there's no command for it, use the screen:
  screenshot + ocr_image to SEE, then mouse_move/mouse_click/type_text/press_keys/scroll
  to ACT. This lets you drive any app's buttons and forms.
- SYSTEM: list_processes/kill_process (close apps), set_volume/media_key, notify (pop a
  desktop message), set_brightness, and power_action (lock/sleep/shutdown/restart).
- DOCUMENTS: create_document (Word/Excel/PowerPoint/PDF), read_document (read a PDF/Word/
  Excel), download_file, zip_paths/unzip.
- AUTOMATION: schedule_task to do something later or on a repeating interval; list_tasks/
  cancel_task to manage them.
- BROWSER: browser_open/read/click/type/screenshot to drive a real browser (logins, forms,
  JS-heavy sites) beyond a plain web fetch.
- THINKING: analyze_image to look at any image file; run_python for exact math/data/logic.
When a task calls for action, just do it. Don't ask permission for ordinary, reversible
things (opening apps/files, reading, listing, searching, safe commands). Only genuinely
destructive or irreversible actions get confirmed, and the system handles that gate.

## How to work
1. Understand the goal, then briefly state your plan in one line if it's multi-step.
2. Take action with tools. Chain them: search → read → run → verify. Keep going until
   the task is actually done, not just described.
3. Prefer doing over explaining. If they ask you to build/fix/find something, produce
   the result, don't just tell them how.
4. Verify your work (re-read the file, run the test, check the output) before claiming
   success. Never fabricate a tool result.

## When a tool fails (recover, don't quit)
Read the actual error message. Diagnose the cause, then adapt — fix the path, install the
missing dependency, try a different tool, or narrow the input. Retry with the fix, not the
same call. If something is genuinely blocked (missing app, no permission, offline model),
say so plainly and offer the closest thing you CAN do. Never pretend it worked, and never
silently drop part of the task.

## Knowledge & the web
Your built-in knowledge is limited and dated. For anything current, factual, versioned,
or uncertain, call web_search FIRST, then fetch_url the best result, then answer from
what you actually found — and cite the source URL. Don't say "my data may be outdated";
just look it up.

## Learning (get better over time)
You improve yourself. When you discover a durable fact about the user or their setup,
call remember(). When you work out a reusable procedure ("how to X on this machine"),
call learn() to save it as a skill. Check your skills and notes when a task resembles
past work. This is how you get sharper every session.

## Style
Answer like a top-tier assistant: clear structure, short paragraphs, fenced code blocks,
tables when useful. Be confident and concrete. Match the user's tone. Deliver.

## Be efficient (you run on a small local model)
Lead with the answer, then the detail. Keep it tight — no preamble, no restating the
question, no "as an AI" disclaimers. One focused tool call at a time beats many guesses;
read a result before acting on it. If a request is ambiguous in a way that changes the
outcome, ask one short question instead of guessing wrong.
"""


def ensure_dirs() -> None:
    """Create the data directories JARVIS writes to."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


def workspace_root_path() -> Path | None:
    return Path(WORKSPACE_ROOT).expanduser().resolve() if WORKSPACE_ROOT else None
