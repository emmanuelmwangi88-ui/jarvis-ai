"""
JARVIS launcher.

  python launch.py

Checks/starts Ollama, warns about any missing models, starts the FastAPI backend
in a background thread, then opens the chat window fullscreen via pywebview. If
pywebview isn't installed, it opens your default browser instead.
"""
from __future__ import annotations

import sys
import threading
import time
import webbrowser

from core import config, memory, ollama_check, rag


def _banner(msg: str) -> None:
    print(f"\n=== {msg} ===")


def _start_backend() -> None:
    from ui.ui_server import run

    run()


def main() -> int:
    config.ensure_dirs()
    memory.init()
    rag.init()

    # Apply the 8GB-safe Ollama server tuning to our own environment first, so a
    # server we spawn inherits it (flash-attention, single loaded model, etc.).
    import os as _os
    _os.environ.update(config.ollama_server_env())

    _banner("Connecting to Ollama")
    try:
        if not ollama_check.start_server():
            print("! Ollama did not come up. Start it manually: `ollama serve`")
    except ollama_check.OllamaError as e:
        print(f"! {e}")
        return 1

    missing = ollama_check.missing_models()
    if missing:
        print("! Missing models (pull them for full functionality):")
        for m in missing:
            print(f"    ollama pull {m}")
    else:
        print("✓ All configured models are installed.")

    _banner(f"Warming up {config.PRIMARY_MODEL} (keeps it hot for fast replies)")
    if ollama_check.preload():
        print("✓ Primary model loaded.")

    _banner("Starting backend")
    t = threading.Thread(target=_start_backend, daemon=True)
    t.start()

    url = f"http://{config.SERVER.host}:{config.SERVER.port}/"
    # give uvicorn a moment to bind
    for _ in range(30):
        time.sleep(0.3)
        try:
            import requests

            if requests.get(url + "api/status", timeout=1).ok:
                break
        except Exception:
            continue
    print(f"✓ Backend on {url}")

    _banner("Opening chat window")
    try:
        import webview  # pywebview

        # Exposed to the page as window.pywebview.api — lets the F11 key toggle
        # the OS window between normal and full-screen (covers the whole screen).
        class _Api:
            def __init__(self) -> None:
                self.win = None

            def toggle_fullscreen(self) -> bool:
                if self.win is not None:
                    self.win.toggle_fullscreen()
                return True

        api = _Api()

        # A normal desktop window: title bar with minimise / maximise / close,
        # freely resizable, with a sensible starting size and a minimum size.
        window = webview.create_window(
            "Sakura AI",
            url,
            width=1280,
            height=820,
            min_size=(900, 600),
            resizable=True,
            fullscreen=False,
            confirm_close=False,
            js_api=api,
        )
        api.win = window
        webview.start()
    except ImportError:
        print("pywebview not installed — opening your browser instead.")
        print("  (pip install pywebview  for the desktop app window)")
        webbrowser.open(url)
        print("\nBackend is running. Press Ctrl+C to quit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nBye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
