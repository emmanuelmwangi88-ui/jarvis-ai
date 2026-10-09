"""
Ollama connectivity: auto-connect, auto-start, and report which configured models
are actually installed. Everything else in the app calls chat()/embed() here.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from typing import Any, Iterator

import requests

from core import config


class OllamaError(RuntimeError):
    pass


# Rolling record of the most recent generation's performance, for the dashboard.
LAST_STATS: dict[str, float] = {
    "tokens_per_sec": 0.0,
    "ttft_ms": 0.0,
    "eval_count": 0.0,
    "total_ms": 0.0,
}


def _record_stats(data: dict[str, Any]) -> None:
    """Extract tokens/sec and TTFT from an Ollama /api/chat response."""
    try:
        eval_count = data.get("eval_count", 0) or 0
        eval_ns = data.get("eval_duration", 0) or 0
        prompt_ns = data.get("prompt_eval_duration", 0) or 0
        total_ns = data.get("total_duration", 0) or 0
        if eval_count and eval_ns:
            LAST_STATS["tokens_per_sec"] = round(eval_count / (eval_ns / 1e9), 1)
            LAST_STATS["eval_count"] = float(eval_count)
        if prompt_ns:
            LAST_STATS["ttft_ms"] = round(prompt_ns / 1e6, 1)
        if total_ns:
            LAST_STATS["total_ms"] = round(total_ns / 1e6, 1)
    except (TypeError, ZeroDivisionError):
        pass


def _url(path: str) -> str:
    host = config.OLLAMA_HOST.strip().rstrip('/')
    # Ollama accepts OLLAMA_HOST values such as 127.0.0.1:11434 as well as
    # full URLs. Normalize both forms so Windows environment settings work.
    if not host.startswith(('http://', 'https://')):
        host = 'http://' + host
    return f"{host}{path}"


def _ollama_executable() -> str | None:
    """Find Ollama even when the Windows installer did not update PATH."""
    found = shutil.which("ollama")
    if found:
        return found
    if sys.platform.startswith("win"):
        import os
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Ollama\ollama.exe"),
            os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Ollama\ollama.exe"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
    return None


def is_up() -> bool:
    """True if Ollama responds, trying common Windows localhost bindings."""
    current = config.OLLAMA_HOST.strip().rstrip('/')
    candidates = [current]
    for host in ("http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"):
        if host not in candidates:
            candidates.append(host)
    for host in candidates:
        url = host if host.startswith(('http://', 'https://')) else 'http://' + host
        try:
            # Bypass inherited proxy settings: Ollama is a local service.
            session = requests.Session()
            session.trust_env = False
            r = session.get(url + "/api/tags", timeout=3)
            if r.status_code == 200:
                config.OLLAMA_HOST = url
                return True
        except requests.RequestException:
            continue
    return False


def start_server(wait_seconds: int = 20) -> bool:
    """
    Start `ollama serve` in the background if the binary exists and the server
    isn't already up. Returns True if the server is up afterwards.
    """
    if is_up():
        # Server already running — our tuning env only applies to a server we
        # start ourselves. Tell the user how to get the 8GB-safe settings.
        import os as _os

        want = config.ollama_server_env()
        missing = {k: v for k, v in want.items() if _os.environ.get(k) != v}
        if missing:
            print(
                "! Ollama is already running, so Sakura's performance env wasn't "
                "applied. For best results on low RAM, stop it and set these first:"
            )
            for k, v in missing.items():
                print(f"    setx {k} {v}   (Windows)   /   export {k}={v}   (mac/Linux)")
        return True
    ollama_bin = _ollama_executable()
    if ollama_bin is None:
        raise OllamaError(
            "Ollama was not found. Install it from https://ollama.com, then restart "
            "Sakura. If it is already installed, add its folder to PATH or start "
            "the Ollama desktop app once."
        )
    # Apply our 8GB-safe tuning to the environment the server inherits.
    import os as _os

    child_env = {**_os.environ, **config.ollama_server_env()}
    # Launch detached; Ollama daemonizes its own model runner.
    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            env=child_env,
        )
    except OSError as e:  # pragma: no cover - platform dependent
        raise OllamaError(f"Failed to launch `ollama serve`: {e}") from e

    for _ in range(wait_seconds):
        if is_up():
            return True
        time.sleep(1)
    return is_up()


def installed_models() -> list[str]:
    """Names of models currently pulled into Ollama (e.g. 'llama3.2:1b')."""
    try:
        r = requests.get(_url("/api/tags"), timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return []


def missing_models() -> list[str]:
    """Configured/required models that are not yet installed."""
    have = set(installed_models())
    # Ollama tags default to ':latest'; compare leniently.
    def present(name: str) -> bool:
        base = name.split(":")[0]
        return name in have or any(h.split(":")[0] == base for h in have)
    return [m for m in config.REQUIRED_MODELS if not present(m)]


def status() -> dict[str, Any]:
    """Snapshot for the UI status indicator."""
    up = is_up()
    have = installed_models() if up else []
    missing = missing_models() if up else config.REQUIRED_MODELS
    return {
        "connected": up,
        "host": config.OLLAMA_HOST,
        "installed": have,
        "required": config.REQUIRED_MODELS,
        "missing": missing,
        "ready": up and not missing,
    }


# --------------------------------------------------------------------------- #
# Thin API wrappers used everywhere else.
# --------------------------------------------------------------------------- #
def chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    images: list[str] | None = None,
    options: dict[str, Any] | None = None,
    keep_alive: str | None = None,
) -> dict[str, Any]:
    """
    Call POST /api/chat (non-streaming) and return the parsed 'message' dict,
    which may contain 'content' and/or 'tool_calls'.

    Default speed options (config.GEN_OPTIONS) and keep_alive (config.KEEP_ALIVE)
    are applied automatically; anything passed in `options` overrides them.
    """
    merged_options = {**config.GEN_OPTIONS, **(options or {})}
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": keep_alive or config.KEEP_ALIVE,
        "options": merged_options,
    }
    if tools:
        payload["tools"] = tools
    if images:
        # attach images to the final user message for vision models
        if payload["messages"] and payload["messages"][-1].get("role") == "user":
            payload["messages"][-1]["images"] = images
    try:
        r = requests.post(
            _url("/api/chat"), json=payload, timeout=config.OLLAMA_REQUEST_TIMEOUT
        )
        r.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(f"Ollama chat call failed: {e}") from e
    data = r.json()
    _record_stats(data)
    return data.get("message", {"role": "assistant", "content": ""})


def chat_stream(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    options: dict[str, Any] | None = None,
    keep_alive: str | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Streaming variant of chat(). Yields dicts:
        {"content": <delta str>, "tool_calls": <list|None>, "done": bool}
    Tokens arrive as they generate. Tool calls (if any) usually arrive in one chunk.
    """
    merged_options = {**config.GEN_OPTIONS, **(options or {})}
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": keep_alive or config.KEEP_ALIVE,
        "options": merged_options,
    }
    if tools:
        payload["tools"] = tools
    try:
        with requests.post(
            _url("/api/chat"), json=payload, stream=True,
            timeout=config.OLLAMA_REQUEST_TIMEOUT,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = data.get("message", {}) or {}
                done = bool(data.get("done"))
                if done:
                    _record_stats(data)
                yield {
                    "content": msg.get("content", "") or "",
                    "tool_calls": msg.get("tool_calls"),
                    "done": done,
                }
    except requests.RequestException as e:
        raise OllamaError(f"Ollama stream call failed: {e}") from e


def unload(model: str | None = None) -> bool:
    """
    Flush a model out of RAM/VRAM by pinging it with keep_alive=0. If no model is
    given, unloads every currently-loaded model. Returns True on success.
    """
    targets = [model] if model else installed_models()
    ok = True
    for m in targets:
        try:
            requests.post(
                _url("/api/chat"),
                json={"model": m, "messages": [], "keep_alive": 0, "stream": False},
                timeout=30,
            )
        except requests.RequestException:
            ok = False
    return ok


def preload(model: str | None = None) -> bool:
    """
    Warm a model into RAM so the first real message isn't slow. Sends an empty
    chat with keep_alive set. Returns True on success, False if it couldn't.
    """
    target = model or config.PRIMARY_MODEL
    try:
        requests.post(
            _url("/api/chat"),
            json={
                "model": target,
                "messages": [],
                "stream": False,
                "keep_alive": config.KEEP_ALIVE,
            },
            timeout=120,
        )
        return True
    except requests.RequestException:
        return False


def embed(model: str, text: str) -> list[float]:
    """Call POST /api/embeddings and return the vector."""
    try:
        r = requests.post(
            _url("/api/embeddings"),
            json={"model": model, "prompt": text},
            timeout=config.OLLAMA_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(f"Ollama embeddings call failed: {e}") from e
    return r.json().get("embedding", [])
