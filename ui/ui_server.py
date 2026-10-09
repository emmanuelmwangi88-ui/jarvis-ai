"""
FastAPI backend for the chat UI.

Endpoints
  GET  /                 -> the chat page (static/index.html)
  GET  /api/status       -> Ollama connection + model readiness (UI polls this)
  POST /api/chat         -> {text, confirm?} -> agent reply (+ pending confirmation)
  POST /api/voice        -> multipart audio -> {transcript, reply, audio_b64}
  POST /api/reflect      -> force a reflect_and_remember pass
  POST /api/reset        -> clear conversation history

Runs local-only by default (127.0.0.1). Nothing here reaches the internet except
tools the model explicitly calls.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import time

from core import agent, config, memory, metrics, ollama_check, rag, voice

STATIC_DIR = Path(__file__).parent / "static"

# When this server process started — used for the "uptime" session stat.
START_TS = time.time()

app = FastAPI(title="JARVIS (local edition)", version="1.0")

# Initialize storage at import time so every entry point (uvicorn, tests, embedding)
# has the tables ready, not only after the ASGI startup event fires.
config.ensure_dirs()
memory.init()
rag.init()


@app.on_event("startup")
def _startup() -> None:
    config.ensure_dirs()
    memory.init()
    rag.init()
    # Connect/start Ollama in the background, then warm the primary model. This
    # also makes launching ui_server directly behave like launch.py.
    import threading

    def connect_and_warm() -> None:
        try:
            if ollama_check.start_server(wait_seconds=12):
                ollama_check.preload()
        except Exception as e:
            print(f"[Sakura] Ollama connection unavailable: {e}")

    threading.Thread(target=connect_and_warm, daemon=True).start()
    # Start the background task scheduler (reminders / recurring instructions).
    try:
        from core import scheduler
        scheduler.start()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class ChatIn(BaseModel):
    text: str
    confirm: bool | None = None  # resolve a pending risky/email action
    images: list[str] = []       # pasted/dropped images as data URLs


class SettingIn(BaseModel):
    key: str
    value: bool


class ProfileIn(BaseModel):
    profile: str


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #
@app.get("/api/status")
def status() -> dict[str, Any]:
    st = ollama_check.status()
    st["rag"] = rag.stats()
    st["autonomy"] = config.AUTONOMY
    st["workspace_lock"] = config.WORKSPACE_ROOT or None
    st["poll_seconds"] = config.SERVER.status_poll_seconds
    st["primary_model"] = config.PRIMARY_MODEL
    st["single_model"] = config.SINGLE_MODEL_MODE
    st["profile"] = config.RUNTIME.get("profile", "trusted")
    st["skills"] = memory.skill_count()
    st["hardware"] = {
        "total_ram_gb": config.TOTAL_RAM_GB,
        "free_ram_gb": config.free_ram_gb(),
        "physical_cores": config.PHYSICAL_CORES,
        "low_ram_mode": config.LOW_RAM_MODE,
        "num_ctx": config.GEN_OPTIONS["num_ctx"],
        "num_threads": config.GEN_OPTIONS["num_thread"],
        "gpu_layers": config.GPU_LAYERS,
    }
    st["perf_tier"] = config.RUNTIME.get("perf_tier", "fast")
    return st


@app.post("/api/perf")
def set_perf(body: dict[str, Any]) -> dict[str, Any]:
    """Switch performance tier (fast/balanced/quality) and/or GPU offload live."""
    changed_model = False
    if "tier" in body:
        before = config.PRIMARY_MODEL
        config.set_perf_tier(str(body["tier"]))
        changed_model = config.PRIMARY_MODEL != before
    if "gpu_layers" in body:
        try:
            config.set_gpu_layers(int(body["gpu_layers"]))
        except (TypeError, ValueError):
            pass
    # Warm the (possibly new) primary so the next reply is fast — but only if the
    # machine has headroom, so we never trigger a low-RAM stall.
    if changed_model and not config.ram_is_tight():
        try:
            ollama_check.preload()
        except Exception:
            pass
    state = config.perf_state()
    state["note"] = (
        "GPU offload needs Ollama restarted with OLLAMA_VULKAN=1 to engage the iGPU."
        if config.GPU_LAYERS > 0 else ""
    )
    return state


@app.get("/api/metrics")
def get_metrics() -> dict[str, Any]:
    """Live CPU / memory / thermal / throughput telemetry for the dashboard."""
    snap = metrics.snapshot()
    snap["connected"] = ollama_check.is_up()
    snap["uptime_s"] = int(time.time() - START_TS)
    return snap


# --------------------------------------------------------------------------- #
# Scheduled tasks (Automation panel) — reads the scheduler's JSON store.
# --------------------------------------------------------------------------- #
@app.get("/api/tasks")
def get_tasks() -> dict[str, Any]:
    try:
        from core import scheduler
        raw = scheduler._load()  # list of {id, instruction, next_run, every_minutes, created}
    except Exception:
        raw = []
    now = time.time()
    tasks = [
        {
            "id": t.get("id"),
            "instruction": t.get("instruction", ""),
            "next_run": t.get("next_run"),
            "in_seconds": max(0, int((t.get("next_run") or now) - now)),
            "every_minutes": t.get("every_minutes"),
        }
        for t in sorted(raw, key=lambda x: x.get("next_run") or 0)
    ]
    return {"tasks": tasks, "count": len(tasks)}


class TaskCancelIn(BaseModel):
    id: str


@app.post("/api/tasks/cancel")
def cancel_task(body: TaskCancelIn) -> dict[str, Any]:
    try:
        from core import scheduler
        msg = scheduler.cancel_task(body.id)
        ok = not msg.startswith("ERROR")
    except Exception as e:  # pragma: no cover
        ok, msg = False, str(e)
    return {"ok": ok, "message": msg}


# --------------------------------------------------------------------------- #
# Models (Model card + quick switcher)
# --------------------------------------------------------------------------- #
@app.get("/api/models")
def get_models() -> dict[str, Any]:
    try:
        installed = ollama_check.installed_models() if ollama_check.is_up() else []
    except Exception:
        installed = []
    h = config.GEN_OPTIONS
    return {
        "installed": installed,
        "primary": config.PRIMARY_MODEL,
        "num_ctx": h.get("num_ctx"),
        "num_predict": h.get("num_predict"),
        "keep_alive": config.RUNTIME.get("keep_alive", getattr(config, "KEEP_ALIVE", "")),
        "single_model": config.SINGLE_MODEL_MODE,
    }


class ModelIn(BaseModel):
    name: str


@app.post("/api/models/retry")
def retry_models() -> dict[str, Any]:
    """Reconnect to Ollama, refresh the model list, and warm the auto-selected model."""
    try:
        connected = ollama_check.is_up()
        if not connected:
            try:
                connected = ollama_check.start_server(wait_seconds=12)
            except Exception as e:
                return {"ok": False, "connected": False, "message": str(e), "installed": []}
        installed = ollama_check.installed_models() if connected else []
        loaded = False
        if connected and config.PRIMARY_MODEL:
            loaded = ollama_check.preload(config.PRIMARY_MODEL)
        return {"ok": connected, "connected": connected, "loaded": loaded,
                "installed": installed, "missing": ollama_check.missing_models() if connected else config.REQUIRED_MODELS,
                "primary": config.PRIMARY_MODEL}
    except Exception as e:
        return {"ok": False, "connected": False, "message": str(e), "installed": []}


@app.post("/api/model")
def set_model(body: ModelIn) -> dict[str, Any]:
    """Swap the active primary model on the fly (from the AI-Core switcher)."""
    name = (body.name or "").strip()
    if not name:
        return {"ok": False, "message": "No model name given."}
    config.PRIMARY_MODEL = name
    if not config.ram_is_tight():
        try:
            ollama_check.preload()
        except Exception:
            pass
    return {"ok": True, "primary": config.PRIMARY_MODEL}


# --------------------------------------------------------------------------- #
# Agent Sandbox settings (the toggles) — these actually gate the tools.
# --------------------------------------------------------------------------- #
@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return {"runtime": dict(config.RUNTIME), "autonomy": config.AUTONOMY}


@app.post("/api/settings")
def set_setting(body: SettingIn) -> dict[str, Any]:
    if body.key in config.RUNTIME:
        config.RUNTIME[body.key] = bool(body.value)
    elif body.key == "yolo":
        config.AUTONOMY = "yolo" if body.value else "safe"
    return {"runtime": dict(config.RUNTIME), "autonomy": config.AUTONOMY}


@app.post("/api/autonomy")
def set_autonomy(body: ProfileIn) -> dict[str, Any]:
    """Switch autonomy profile: trusted | unleashed | locked."""
    profile = config.set_profile(body.profile)
    return {"profile": profile, "autonomy": config.AUTONOMY, "runtime": dict(config.RUNTIME)}


@app.get("/api/learning")
def learning() -> dict[str, Any]:
    """Self-learning snapshot: notes + skills for the UI panel."""
    return {
        "skills": memory.all_skills(),
        "notes": [n["content"] for n in memory.all_notes()][-20:],
        "skill_count": memory.skill_count(),
    }


@app.post("/api/unload")
def unload_models() -> dict[str, Any]:
    """Flush models out of RAM/VRAM ('Flush VRAM Cache')."""
    ok = ollama_check.unload()
    return {"ok": ok, "message": "Model cache flushed." if ok else "Nothing to flush / Ollama offline."}


@app.post("/api/benchmark")
def benchmark() -> dict[str, Any]:
    """Time a tiny generation and report throughput ('Run System Benchmark')."""
    t0 = time.time()
    try:
        ollama_check.chat(
            config.PRIMARY_MODEL,
            [{"role": "user", "content": "Reply with the single word: ok"}],
            options={"num_predict": 8},
        )
    except ollama_check.OllamaError as e:
        return {"ok": False, "message": str(e)}
    elapsed = round((time.time() - t0) * 1000)
    return {
        "ok": True,
        "elapsed_ms": elapsed,
        "tokens_per_sec": ollama_check.LAST_STATS.get("tokens_per_sec", 0.0),
        "ttft_ms": ollama_check.LAST_STATS.get("ttft_ms", 0.0),
        "model": config.PRIMARY_MODEL,
        "message": f"{config.PRIMARY_MODEL}: {ollama_check.LAST_STATS.get('tokens_per_sec', 0)} t/s, round-trip {elapsed}ms",
    }


@app.get("/api/history")
def history(limit: int = 200) -> dict[str, Any]:
    """Full recent transcript (with timestamps + model) for the Recent Chats view."""
    return {"messages": memory.transcript(limit=limit)}


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #
def _serialize(result: agent.AgentResult) -> dict[str, Any]:
    return {
        "reply": result.reply,
        "role": result.role,
        "model": result.model,
        "tool_calls": result.tool_calls,
        "needs_confirmation": result.needs_confirmation,
    }


@app.post("/api/chat")
def chat(body: ChatIn) -> dict[str, Any]:
    result = agent.handle_message(body.text, confirm=body.confirm)
    return _serialize(result)


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn) -> StreamingResponse:
    """Server-Sent Events: streams tokens, tool calls, and confirmations live."""
    def gen():
        try:
            for ev in agent.handle_message_stream(body.text, confirm=body.confirm, images=body.images):
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:  # never break the stream ungracefully
            yield f"data: {json.dumps({'t': 'error', 'message': str(e)})}\n\n"
        yield "data: {\"t\": \"end\"}\n\n"
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- #
# Voice
# --------------------------------------------------------------------------- #
@app.post("/api/voice")
async def voice_turn(audio: UploadFile = File(...), confirm: str = Form("")) -> JSONResponse:
    raw = await audio.read()
    try:
        transcript = voice.transcribe(raw)
    except Exception as e:  # missing deps, decode errors, etc.
        return JSONResponse(
            {"error": f"transcription failed: {e}"}, status_code=500
        )
    if not transcript:
        return JSONResponse({"transcript": "", "reply": "I didn't catch that.", "audio_b64": ""})

    conf = None if confirm == "" else (confirm.lower() == "true")
    result = agent.handle_message(transcript, confirm=conf)

    wav = voice.synthesize(result.reply) if config.RUNTIME.get("audio", True) else b""
    audio_b64 = base64.b64encode(wav).decode("ascii") if wav else ""
    payload = _serialize(result)
    payload.update({"transcript": transcript, "audio_b64": audio_b64})
    return JSONResponse(payload)


# --------------------------------------------------------------------------- #
# Maintenance
# --------------------------------------------------------------------------- #
@app.post("/api/reflect")
def reflect() -> dict[str, str]:
    return {"result": agent.reflect_and_remember()}


@app.post("/api/reset")
def reset() -> dict[str, str]:
    # Start a fresh chat but KEEP past chats browsable in Recent Chats.
    memory.new_session()
    return {"result": "Started a new chat."}


# --------------------------------------------------------------------------- #
# Chat sessions (Recent Chats — browse & reopen past conversations)
# --------------------------------------------------------------------------- #
@app.get("/api/sessions")
def get_sessions() -> dict[str, Any]:
    return {"sessions": memory.list_sessions()}


class SessionIn(BaseModel):
    id: int


class SessionTitleIn(BaseModel):
    id: int
    title: str | None = None
    improve: bool = False


@app.post("/api/sessions/load")
def load_session(body: SessionIn) -> dict[str, Any]:
    memory.load_session(body.id)
    return {"ok": True, "id": body.id, "messages": memory.session_transcript(body.id)}


@app.post("/api/sessions/new")
def new_session() -> dict[str, Any]:
    sid = memory.new_session()
    return {"ok": True, "id": sid}


@app.post("/api/sessions/title")
def title_session(body: SessionTitleIn) -> dict[str, Any]:
    """Set a title, or ask the local model for a concise searchable title."""
    title = (body.title or "").strip()
    if body.improve or not title:
        msgs = memory.session_transcript(body.id, limit=8)
        context = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in msgs)
        try:
            answer = ollama_check.chat(config.PRIMARY_MODEL, [{"role": "user", "content":
                "Create a short, specific chat title. Return only 3-7 words, no quotes, no punctuation.\n" + context}],
                options={"temperature": 0.2, "num_predict": 24})
            title = (answer.get("content") or "").strip().splitlines()[0][:90]
        except Exception:
            title = memory.session_title(body.id)
    memory.set_session_title(body.id, title)
    return {"ok": True, "id": body.id, "title": title}


# static assets (js/css/images if you add any) under /static
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run() -> None:
    """Entry point used by launch.py."""
    import uvicorn

    uvicorn.run(
        app,
        host=config.SERVER.host,
        port=config.SERVER.port,
        log_level="warning",
    )


if __name__ == "__main__":
    run()
