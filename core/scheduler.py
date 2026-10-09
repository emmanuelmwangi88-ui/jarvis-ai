"""
Lightweight task scheduler for Sakura.

Lets the agent schedule an instruction to run later or on a repeating interval.
Tasks persist to DATA_DIR/scheduler.json so they survive restarts. A single
background thread wakes periodically, runs any due tasks by feeding the stored
instruction back through the agent, notifies the user, and reschedules or drops
the task. Kept deliberately simple — no external cron dependency.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core import config

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STARTED = False


def _path() -> Path:
    return config.DATA_DIR / "scheduler.json"


def _load() -> list[dict[str, Any]]:
    try:
        return json.loads(_path().read_text())
    except Exception:
        return []


def _save(tasks: list[dict[str, Any]]) -> None:
    try:
        _path().parent.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(tasks, indent=2))
    except Exception:
        pass


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def add_task(instruction: str, run_in_minutes: int | None = None,
             at: str | None = None, every_minutes: int | None = None) -> str:
    now = time.time()
    next_run = now + 60  # sensible default: ~1 min out
    if run_in_minutes is not None:
        next_run = now + float(run_in_minutes) * 60
    elif at:
        try:
            hh, mm = [int(x) for x in str(at).split(":")[:2]]
            target = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target.timestamp() <= now:
                target += timedelta(days=1)
            next_run = target.timestamp()
        except Exception:
            return "ERROR: couldn't parse 'at' — use 'HH:MM' (24-hour)."
    elif every_minutes is not None:
        next_run = now + float(every_minutes) * 60

    task = {
        "id": uuid.uuid4().hex[:8],
        "instruction": instruction,
        "next_run": next_run,
        "every_minutes": int(every_minutes) if every_minutes else None,
        "created": now,
    }
    with _LOCK:
        tasks = _load(); tasks.append(task); _save(tasks)
    start()  # ensure the runner is alive
    rep = f"every {every_minutes} min" if every_minutes else f"at {_fmt(next_run)}"
    return f"Scheduled task {task['id']} ({rep}): {instruction[:80]}"


def list_tasks() -> str:
    with _LOCK:
        tasks = _load()
    if not tasks:
        return "No scheduled tasks."
    lines = []
    for t in tasks:
        rep = f"every {t['every_minutes']}m" if t.get("every_minutes") else "once"
        lines.append(f"[{t['id']}] {rep} · next {_fmt(t['next_run'])} · {t['instruction'][:70]}")
    return "\n".join(lines)


def cancel_task(task_id: str) -> str:
    with _LOCK:
        tasks = _load()
        keep = [t for t in tasks if t["id"] != task_id]
        if len(keep) == len(tasks):
            return f"ERROR: no task with id '{task_id}'."
        _save(keep)
    return f"Cancelled task {task_id}."


def _run_due() -> None:
    now = time.time()
    with _LOCK:
        tasks = _load()
    due = [t for t in tasks if t["next_run"] <= now]
    for t in due:
        # Don't risk a heavy agent turn when RAM is critically tight.
        if config.ram_is_tight():
            continue
        try:
            from core import agent  # lazy to avoid import cycle
            result = agent.handle_message(f"[Scheduled task] {t['instruction']}")
            reply = getattr(result, "reply", str(result))
        except Exception as e:
            reply = f"(task error: {e})"
        try:
            from tools import tools as toolmod
            toolmod.notify("Sakura task done", (t["instruction"][:60]))
        except Exception:
            pass
        with _LOCK:
            tasks = _load()
            for cur in tasks:
                if cur["id"] != t["id"]:
                    continue
                if cur.get("every_minutes"):
                    cur["next_run"] = time.time() + cur["every_minutes"] * 60
                    cur["last_result"] = (reply or "")[:200]
                else:
                    tasks = [x for x in tasks if x["id"] != t["id"]]
                break
            _save(tasks)


def _loop() -> None:
    while True:
        try:
            _run_due()
        except Exception:
            pass
        time.sleep(20)


def start() -> None:
    """Start the background runner once (idempotent)."""
    global _THREAD, _STARTED
    if _STARTED and _THREAD and _THREAD.is_alive():
        return
    _STARTED = True
    _THREAD = threading.Thread(target=_loop, daemon=True)
    _THREAD.start()
