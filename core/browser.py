"""
Browser automation for Sakura, backed by Playwright (Chromium).

Keeps ONE browser + page alive across tool calls so the agent can navigate, read,
click and type across a multi-step session (including sites needing JavaScript or a
login). Playwright is an optional dependency — every function degrades to a friendly
message telling the user how to install it rather than crashing.

Install:
    pip install playwright
    playwright install chromium
"""
from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_PW: Any = None       # the playwright context manager handle
_BROWSER: Any = None
_PAGE: Any = None


def _hint() -> str:
    return ("ERROR: browser automation needs Playwright. Install it with:\n"
            "    pip install playwright\n"
            "    playwright install chromium")


def _ensure() -> str | None:
    """Make sure a browser + page exist. Returns an error string or None."""
    global _PW, _BROWSER, _PAGE
    if _PAGE is not None:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return _hint()
    try:
        _PW = sync_playwright().start()
        _BROWSER = _PW.chromium.launch(headless=True)
        _PAGE = _BROWSER.new_page()
        return None
    except Exception as e:
        return (f"ERROR: couldn't launch Chromium ({e}). "
                "Run:  playwright install chromium")


def open_page(url: str) -> str:
    with _LOCK:
        err = _ensure()
        if err:
            return err
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            _PAGE.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = _PAGE.title()
            body = (_PAGE.inner_text("body") or "").strip()
            return f"Opened {url}\nTitle: {title}\n\n{body[:2500]}"
        except Exception as e:
            return f"ERROR: browser_open failed: {e}"


def read_text() -> str:
    with _LOCK:
        if _PAGE is None:
            return "ERROR: no page open. Call browser_open first."
        try:
            body = (_PAGE.inner_text("body") or "").strip()
            return body[:4000] or "(empty page)"
        except Exception as e:
            return f"ERROR: browser_read failed: {e}"


def click(target: str) -> str:
    with _LOCK:
        if _PAGE is None:
            return "ERROR: no page open. Call browser_open first."
        try:
            try:
                _PAGE.get_by_text(target, exact=False).first.click(timeout=6000)
            except Exception:
                _PAGE.click(target, timeout=6000)  # fall back to CSS selector
            _PAGE.wait_for_load_state("domcontentloaded", timeout=8000)
            return f"Clicked '{target}'. Now at: {_PAGE.url}"
        except Exception as e:
            return f"ERROR: browser_click failed: {e}"


def type_into(target: str, text: str, submit: bool = False) -> str:
    with _LOCK:
        if _PAGE is None:
            return "ERROR: no page open. Call browser_open first."
        try:
            try:
                _PAGE.fill(target, text, timeout=6000)
            except Exception:
                _PAGE.get_by_placeholder(target).first.fill(text, timeout=6000)
            if submit:
                _PAGE.keyboard.press("Enter")
                _PAGE.wait_for_load_state("domcontentloaded", timeout=8000)
            return f"Typed into '{target}'{' and submitted' if submit else ''}."
        except Exception as e:
            return f"ERROR: browser_type failed: {e}"


def shot(path: str | None = None) -> str:
    with _LOCK:
        if _PAGE is None:
            return "ERROR: no page open. Call browser_open first."
        try:
            from core import config
            out = path or str(config.DATA_DIR / "browser.png")
            _PAGE.screenshot(path=out, full_page=True)
            return f"Saved page screenshot to {out}"
        except Exception as e:
            return f"ERROR: browser_screenshot failed: {e}"


def shutdown() -> None:
    global _PW, _BROWSER, _PAGE
    try:
        if _BROWSER:
            _BROWSER.close()
        if _PW:
            _PW.stop()
    except Exception:
        pass
    _PW = _BROWSER = _PAGE = None
