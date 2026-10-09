"""
Live system telemetry for the dashboard cards (CPU, memory, thermals, throughput).
Uses psutil when available; degrades gracefully to /proc or zeros so the endpoint
never crashes on a machine without psutil.
"""
from __future__ import annotations

import os
from typing import Any

from core import ollama_check

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore


def _mem() -> tuple[float, float, float]:
    """(used_gb, total_gb, percent)."""
    if psutil:
        vm = psutil.virtual_memory()
        return (
            round((vm.total - vm.available) / 1e9, 2),
            round(vm.total / 1e9, 2),
            round(vm.percent, 1),
        )
    # /proc fallback (Linux)
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k] = int(v.strip().split()[0]) * 1024  # kB -> bytes
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", 0)
        used = total - avail
        pct = round(100 * used / total, 1) if total else 0.0
        return round(used / 1e9, 2), round(total / 1e9, 2), pct
    except OSError:
        return 0.0, 0.0, 0.0


def _cpu() -> tuple[float, list[float]]:
    """(overall_percent, per_core_percent)."""
    if psutil:
        per = psutil.cpu_percent(interval=0.15, percpu=True)
        overall = round(sum(per) / len(per), 1) if per else 0.0
        return overall, [round(x, 1) for x in per]
    try:
        load1 = os.getloadavg()[0]
        cores = os.cpu_count() or 1
        overall = round(min(100.0, 100 * load1 / cores), 1)
        return overall, [overall]
    except (OSError, AttributeError):
        return 0.0, [0.0]


def _temp() -> float | None:
    """Best-effort CPU temperature in °C, or None if unavailable."""
    if not psutil or not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return None
    for _name, entries in (temps or {}).items():
        for e in entries:
            if e.current:
                return round(float(e.current), 1)
    return None


def snapshot() -> dict[str, Any]:
    cpu_pct, per_core = _cpu()
    used_gb, total_gb, mem_pct = _mem()
    temp = _temp()
    return {
        "cpu_percent": cpu_pct,
        "cpu_cores": len(per_core),
        "cpu_per_core": per_core,
        "mem_used_gb": used_gb,
        "mem_total_gb": total_gb,
        "mem_percent": mem_pct,
        "temp_c": temp,
        "tokens_per_sec": ollama_check.LAST_STATS.get("tokens_per_sec", 0.0),
        "ttft_ms": ollama_check.LAST_STATS.get("ttft_ms", 0.0),
        "pid": os.getpid(),
    }
