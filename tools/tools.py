"""
Every real action JARVIS can take, the JSON schema Ollama uses to call them, and
the name->function registry the agent loop dispatches through.

To add a capability:
  1. write a function here that returns a string (what the model "sees" as result),
  2. add its schema to TOOLS_SCHEMA,
  3. register it in TOOL_FUNCTIONS.
No change to core/agent.py is needed.

Design notes:
- Every tool returns a plain string. Errors are returned as strings starting with
  "ERROR:" rather than raised, so the model can react instead of the loop crashing.
- File tools respect config.WORKSPACE_ROOT (the workspace lock).
- Windows-only tools degrade gracefully on other platforms.
"""
from __future__ import annotations

import os
import platform
import shutil
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

import requests

from core import config, memory, rag

IS_WINDOWS = sys.platform.startswith("win")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _err(msg: str) -> str:
    return f"ERROR: {msg}"


def _resolve_in_workspace(path: str) -> Path | str:
    """
    Resolve a user path and enforce the workspace lock. Returns a Path on success
    or an error string if the path escapes the allowed root.
    """
    p = Path(path).expanduser()
    root = config.workspace_root_path()
    if root is None:
        return p.resolve()
    try:
        resolved = p.resolve()
        resolved.relative_to(root)
        return resolved
    except (ValueError, OSError):
        return _err(
            f"path '{path}' is outside the locked workspace ({root}). "
            "Refusing to touch it."
        )


# --------------------------------------------------------------------------- #
# Filesystem
# --------------------------------------------------------------------------- #
def list_dir(path: str = ".") -> str:
    p = _resolve_in_workspace(path)
    if isinstance(p, str):
        return p
    if not p.exists():
        return _err(f"no such path: {path}")
    if p.is_file():
        return f"{p} (file, {p.stat().st_size} bytes)"
    entries = []
    for child in sorted(p.iterdir()):
        kind = "dir " if child.is_dir() else "file"
        size = "" if child.is_dir() else f"  {child.stat().st_size}b"
        entries.append(f"{kind}  {child.name}{size}")
    return f"{p}:\n" + ("\n".join(entries) if entries else "(empty)")


def read_file(path: str, max_bytes: int = 100_000) -> str:
    p = _resolve_in_workspace(path)
    if isinstance(p, str):
        return p
    if not p.is_file():
        return _err(f"not a file: {path}")
    try:
        data = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return _err(str(e))
    if len(data) > max_bytes:
        return data[:max_bytes] + f"\n...[truncated at {max_bytes} bytes]"
    return data


def write_file(path: str, content: str, overwrite: bool = False) -> str:
    if not config.RUNTIME.get("fs_write", True):
        return _err("filesystem writes are disabled in the Agent Sandbox settings.")
    p = _resolve_in_workspace(path)
    if isinstance(p, str):
        return p
    if p.exists() and not overwrite:
        return _err(
            f"{path} already exists. Call again with overwrite=true to replace it."
        )
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as e:
        return _err(str(e))
    return f"Wrote {len(content)} bytes to {p}."


def search_files(pattern: str, path: str = ".") -> str:
    p = _resolve_in_workspace(path)
    if isinstance(p, str):
        return p
    if not p.is_dir():
        return _err(f"not a directory: {path}")
    matches = [str(m) for m in p.rglob(pattern)][:200]
    return "\n".join(matches) if matches else f"No files matching '{pattern}' under {p}."


# --------------------------------------------------------------------------- #
# Terminal
# --------------------------------------------------------------------------- #
# Substrings that mark a command as risky -> triggers the confirmation gate.
_RISKY_TOKENS = (
    "rm ", "rmdir", "del ", "format", "mkfs", "dd ", "shutdown", "reboot",
    ":(){", "> /dev", "sudo", "rd /s", "diskpart", "reg delete", "chmod -r",
    "chown -r", "git reset --hard", "git clean", "curl", "wget", "powershell",
    "move ", "mv ", "rename",
)


def is_risky_command(command: str) -> bool:
    low = command.lower()
    return any(tok in low for tok in _RISKY_TOKENS)


def run_command(command: str, confirmed: bool = False) -> str:
    """
    Run a shell command. Risky commands require confirmed=true unless AUTONOMY
    is 'yolo'. When a risky command is blocked, the returned string tells the
    agent to obtain confirmation — the UI/CLI surfaces that to the human.
    """
    if not config.RUNTIME.get("shell", True):
        return _err("shell execution is disabled in the Agent Sandbox settings.")
    if is_risky_command(command) and config.AUTONOMY != "yolo" and not confirmed:
        return (
            "CONFIRM_REQUIRED: this looks risky. "
            f"Command: {command!r}. "
            "Ask the user to confirm, then call run_command again with confirmed=true."
        )
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return _err("command timed out after 120s")
    except OSError as e:
        return _err(str(e))
    out = proc.stdout or ""
    errtxt = proc.stderr or ""
    tail = (out + ("\n[stderr]\n" + errtxt if errtxt else "")).strip()
    if len(tail) > 8000:
        tail = tail[:8000] + "\n...[truncated]"
    return f"(exit {proc.returncode})\n{tail}" if tail else f"(exit {proc.returncode}) [no output]"


# --------------------------------------------------------------------------- #
# Clipboard
# --------------------------------------------------------------------------- #
def read_clipboard() -> str:
    try:
        import pyperclip

        return pyperclip.paste() or "(clipboard empty)"
    except Exception as e:  # pyperclip raises broad errors on headless systems
        return _err(f"clipboard unavailable: {e}")


def write_clipboard(text: str) -> str:
    try:
        import pyperclip

        pyperclip.copy(text)
        return "Copied to clipboard."
    except Exception as e:
        return _err(f"clipboard unavailable: {e}")


# --------------------------------------------------------------------------- #
# Windows / apps (Windows-only; graceful elsewhere)
# --------------------------------------------------------------------------- #
def list_windows() -> str:
    if not IS_WINDOWS:
        return _err("window control is Windows-only on this build.")
    try:
        from pywinauto import Desktop

        titles = [
            w.window_text()
            for w in Desktop(backend="uia").windows()
            if w.window_text().strip()
        ]
        return "\n".join(dict.fromkeys(titles)) or "(no titled windows)"
    except Exception as e:
        return _err(f"pywinauto failed: {e}")


def focus_window(title: str) -> str:
    if not IS_WINDOWS:
        return _err("window control is Windows-only on this build.")
    try:
        from pywinauto import Desktop

        win = Desktop(backend="uia").window(title_re=f".*{title}.*")
        win.set_focus()
        return f"Focused window matching '{title}'."
    except Exception as e:
        return _err(f"couldn't focus '{title}': {e}")


def _find_start_menu(name: str) -> str | None:
    """Search Windows Start Menu .lnk shortcuts for a name substring."""
    roots = [
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]
    nl = name.lower()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".lnk") and nl in f.lower():
                    return os.path.join(dirpath, f)
    return None


def open_app(name_or_path: str) -> str:
    """
    Open an application by name (e.g. 'Roblox', 'Spotify', 'Chrome') or open a
    file/folder/URL. On Windows this resolves real installed apps (Store + desktop)
    via Get-StartApps, then falls back to shell start / PATH / Start-Menu shortcuts.
    """
    target = (name_or_path or "").strip().strip('"')
    if not target:
        return _err("nothing to open")

    # 1) A URL -> browser (respects the web toggle).
    if target.startswith(("http://", "https://")):
        return open_url(target)

    # 2) An existing path -> default handler.
    p = Path(target).expanduser()
    if p.exists():
        try:
            if IS_WINDOWS:
                os.startfile(str(p))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return f"Opened {p}"
        except OSError as e:
            return _err(str(e))

    # 3) Non-Windows: hand the name to the OS opener.
    if not IS_WINDOWS:
        try:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, target])
            return f"Opened: {target}"
        except OSError as e:
            return _err(str(e))

    # 4) Windows: resolve the app by name via Get-StartApps (covers Roblox, Store apps,
    #    and most desktop apps registered in the Start menu).
    safe = target.replace("'", "''")
    ps = (
        f"$n='{safe}';"
        "$a=Get-StartApps | Where-Object {$_.Name -like ('*'+$n+'*')} | Select-Object -First 1;"
        "if($a){Start-Process ('shell:AppsFolder\\'+$a.AppID); Write-Output ('OK:'+$a.Name)}"
        "else{exit 2}"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0 and "OK:" in (r.stdout or ""):
            return f"Opened app: {r.stdout.strip().split('OK:')[-1]}"
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 5) `start` (uses PATH + file associations).
    try:
        subprocess.run(["cmd", "/c", "start", "", target], timeout=15)
        return f"Launched '{target}'."
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 6) `where` -> executable path.
    try:
        w = subprocess.run(["where", target], capture_output=True, text=True, timeout=10)
        if w.returncode == 0 and w.stdout.strip():
            exe = w.stdout.strip().splitlines()[0]
            os.startfile(exe)  # type: ignore[attr-defined]
            return f"Opened {exe}"
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 7) Start-Menu shortcut search.
    lnk = _find_start_menu(target)
    if lnk:
        try:
            os.startfile(lnk)  # type: ignore[attr-defined]
            return f"Opened {Path(lnk).stem} (Start Menu)"
        except OSError:
            pass

    return _err(
        f"Couldn't find an app or file named '{target}'. "
        "Give me the exact app name or a full path, and I'll open it."
    )


def open_path(path: str) -> str:
    """Open a file with its default app, or reveal/open a folder."""
    return open_app(path)


# directories that are noise or dangerous to walk when searching
_SKIP_DIRS = {
    "windows", "$recycle.bin", "program files", "program files (x86)", "programdata",
    "node_modules", "__pycache__", ".git", "venv", ".venv", ".cache",
    "temp", "tmp", "system volume information", "appdata",
}


def find_files(query: str, root: str | None = None, max_results: int = 30) -> str:
    """
    Find files by name or glob under the user's common folders (Desktop, Documents,
    Downloads, …) or a given root. Bounded (12s / result cap) so it never hangs.
    Returns matching full paths, best for feeding into open_app/open_path/delete_path.
    """
    import fnmatch
    import time as _time

    q = (query or "").strip()
    if not q:
        return _err("empty search query")

    if root:
        rp = _resolve_in_workspace(root)
        if isinstance(rp, str):
            return rp
        roots = [Path(rp)]
    else:
        home = Path.home()
        roots = [home / d for d in
                 ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")]
        roots.append(home)

    is_glob = any(c in q for c in "*?[")
    ql = q.lower()
    results: list[str] = []
    seen: set[str] = set()
    scanned = 0
    start = _time.time()

    for r in roots:
        if not r.exists():
            continue
        for dirpath, dirs, files in os.walk(r):
            if _time.time() - start > 12 or len(results) >= max_results:
                break
            dirs[:] = [d for d in dirs
                       if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            for f in files:
                scanned += 1
                ok = fnmatch.fnmatch(f.lower(), ql) if is_glob else (ql in f.lower())
                if ok:
                    full = str(Path(dirpath) / f)
                    if full not in seen:
                        seen.add(full)
                        results.append(full)
                        if len(results) >= max_results:
                            break
        if _time.time() - start > 12 or len(results) >= max_results:
            break

    if not results:
        return f"No files matching '{query}' (searched {scanned} files)."
    more = " (showing first %d)" % max_results if len(results) >= max_results else ""
    return f"Found {len(results)} match(es) for '{query}'{more}:\n" + "\n".join(results)


def delete_path(path: str, confirmed: bool = False) -> str:
    """
    Delete a file or folder. Requires confirmed=true unless autonomy is 'yolo'
    (the agent's confirmation gate handles asking the human). Permanent.
    """
    if not config.RUNTIME.get("fs_write", True):
        return _err("filesystem writes/deletes are disabled in the Agent Sandbox settings.")
    p = _resolve_in_workspace(path)
    if isinstance(p, str):
        return p
    if not p.exists():
        return _err(f"no such path: {path}")
    if config.AUTONOMY != "yolo" and not confirmed:
        return (
            f"CONFIRM_REQUIRED: permanently delete {p}? "
            "Ask the user to confirm, then call delete_path again with confirmed=true."
        )
    try:
        if p.is_dir():
            shutil.rmtree(p)
            return f"Deleted folder {p}."
        p.unlink()
        return f"Deleted file {p}."
    except OSError as e:
        return _err(str(e))


# --------------------------------------------------------------------------- #
# Browser / web
# --------------------------------------------------------------------------- #
def open_url(url: str) -> str:
    if not config.RUNTIME.get("web", True):
        return _err("outbound internet is disabled in the Agent Sandbox settings.")
    import webbrowser

    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url} in your browser."


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _clean_ddg_url(href: str) -> str:
    """DuckDuckGo wraps result links as //duckduckgo.com/l/?uddg=<encoded>. Unwrap it."""
    if not href:
        return href
    if "uddg=" in href:
        try:
            q = parse_qs(urlparse(href).query)
            if "uddg" in q:
                return unquote(q["uddg"][0])
        except (ValueError, KeyError):
            pass
    if href.startswith("//"):
        return "https:" + href
    return href


def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web via DuckDuckGo (no API key) and return ranked results as
    'N. Title\\n   url\\n   snippet'. Use fetch_url on a result to read it fully.
    """
    if not config.RUNTIME.get("web", True):
        return _err("outbound internet is disabled in the Agent Sandbox settings.")
    query = (query or "").strip()
    if not query:
        return _err("empty search query")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _err("web search needs beautifulsoup4 (pip install beautifulsoup4)")

    endpoints = [
        ("https://html.duckduckgo.com/html/", ".result", "a.result__a", ".result__snippet"),
        ("https://lite.duckduckgo.com/lite/", "tr", "a.result-link", ".result-snippet"),
    ]
    last_err = ""
    for url, row_sel, link_sel, snip_sel in endpoints:
        try:
            r = requests.post(
                url, data={"q": query}, timeout=20,
                headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
            )
            r.raise_for_status()
        except requests.RequestException as e:
            last_err = str(e)
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        results: list[str] = []
        for row in soup.select(row_sel):
            a = row.select_one(link_sel)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            link = _clean_ddg_url(a.get("href", ""))
            if not title or not link.startswith("http"):
                continue
            snip_el = row.select_one(snip_sel)
            snippet = snip_el.get_text(" ", strip=True) if snip_el else ""
            n = len(results) + 1
            results.append(f"{n}. {title}\n   {link}\n   {snippet}".rstrip())
            if len(results) >= max_results:
                break
        if results:
            return f"Top results for {query!r}:\n\n" + "\n\n".join(results)

    return _err(f"no results (or search blocked). {last_err}".strip())


def fetch_url(url: str, max_chars: int = 6000) -> str:
    """GET a page and return a rough text extraction (no JS execution)."""
    if not config.RUNTIME.get("web", True):
        return _err("outbound internet is disabled in the Agent Sandbox settings.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": _UA})
        r.raise_for_status()
    except requests.RequestException as e:
        return _err(str(e))
    text = r.text
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())
    except Exception:
        pass  # fall back to raw HTML
    return text[:max_chars] + ("\n...[truncated]" if len(text) > max_chars else "")


# --------------------------------------------------------------------------- #
# Screen
# --------------------------------------------------------------------------- #
def screenshot(path: str | None = None) -> str:
    """Capture every visible monitor to a PNG for the vision model."""
    if not config.RUNTIME.get("desktop", True):
        return _err("desktop access is disabled (Desktop capability is off).")
    try:
        from PIL import ImageGrab

        # all_screens is supported by Pillow on Windows and captures the full
        # virtual desktop, including monitors left of the primary display.
        try:
            img = ImageGrab.grab(all_screens=True)
        except TypeError:
            img = ImageGrab.grab()
    except Exception as e:
        return _err(f"screenshot failed: {e}")
    out = Path(path).expanduser() if path else (config.DATA_DIR / "last_screenshot.png")
    config.ensure_dirs()
    img.save(out)
    return str(out)


def ocr_image(path: str) -> str:
    """Extract text from an image with Tesseract (must be installed)."""
    p = Path(path).expanduser()
    if not p.is_file():
        return _err(f"no such image: {path}")
    try:
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(p)).strip() or "(no text found)"
    except Exception as e:
        return _err(f"OCR failed (is Tesseract installed?): {e}")


# --------------------------------------------------------------------------- #
# Email (always confirmed)
# --------------------------------------------------------------------------- #
def send_email(to: str, subject: str, body: str, confirmed: bool = False) -> str:
    if not config.EMAIL.configured:
        return _err(
            "email not configured. Set sender_email + app_password in core/config.py "
            "(or JARVIS_EMAIL / JARVIS_EMAIL_PASSWORD env vars)."
        )
    if not confirmed:
        return (
            "CONFIRM_REQUIRED: sending email always needs confirmation. "
            f"To: {to} | Subject: {subject!r}. "
            "Ask the user to confirm, then call send_email again with confirmed=true."
        )
    msg = EmailMessage()
    msg["From"] = config.EMAIL.sender_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.EMAIL.smtp_host, config.EMAIL.smtp_port, timeout=30) as s:
            s.starttls()
            s.login(config.EMAIL.sender_email, config.EMAIL.app_password)
            s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        return _err(f"send failed: {e}")
    return f"Email sent to {to}."


# --------------------------------------------------------------------------- #
# Memory / knowledge
# --------------------------------------------------------------------------- #
def remember(note: str) -> str:
    memory.add_note(note)
    return "Saved. I'll keep that in mind for future sessions."


def recall_notes() -> str:
    notes = memory.all_notes()
    if not notes:
        return "No saved notes yet."
    return "\n".join(f"- {n['content']}" for n in notes)


def learn(name: str, content: str) -> str:
    """Save a reusable skill/procedure the assistant taught itself."""
    memory.add_skill(name.strip()[:80], content.strip())
    return f"Learned skill '{name}'. I'll reuse it for similar tasks."


def skills() -> str:
    """List self-taught skills."""
    sk = memory.all_skills()
    if not sk:
        return "No skills learned yet."
    return "\n".join(f"- {s['name']} (used {s['uses']}x): {s['content']}" for s in sk)


def remember_document(path: str) -> str:
    return rag.remember_document(path)


def search_knowledge(query: str) -> str:
    return rag.search_knowledge(query)


def system_info() -> str:
    return (
        f"OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
        f"Python: {platform.python_version()}\n"
        f"CPU cores: {os.cpu_count()}\n"
        f"Autonomy: {config.AUTONOMY} | Desktop access: {bool(config.RUNTIME.get('desktop', True))} | "
        f"Workspace lock: {config.WORKSPACE_ROOT or 'off'}"
    )


# --------------------------------------------------------------------------- #
# Optional-dependency helper
# --------------------------------------------------------------------------- #
def _optional(mod: str, pip_name: str | None = None):
    """Import an optional dependency, or return None. Callers give a friendly hint."""
    try:
        return __import__(mod)
    except Exception:
        return None


def _need(mod_disp: str, pip_name: str) -> str:
    return _err(f"{mod_disp} isn't available. Install it with:  pip install {pip_name}")


# --------------------------------------------------------------------------- #
# Pack 1 — Computer control (mouse + keyboard) via pyautogui
#   Gated behind RUNTIME['shell'] since it's real machine control.
# --------------------------------------------------------------------------- #
def _pyautogui():
    pg = _optional("pyautogui")
    if pg is not None:
        try:
            pg.FAILSAFE = False
        except Exception:
            pass
    return pg


def _control_allowed() -> str | None:
    # Desktop control is independent from terminal control: the user can allow
    # Sakura to see/click/type in graphical apps without allowing shell commands.
    if not config.RUNTIME.get("desktop", True):
        return _err("desktop control is disabled (Desktop capability is off).")
    return None


def mouse_move(x: int, y: int) -> str:
    if (g := _control_allowed()):
        return g
    pg = _pyautogui()
    if pg is None:
        return _need("pyautogui (mouse/keyboard control)", "pyautogui")
    try:
        pg.moveTo(int(x), int(y), duration=0.15)
        return f"Moved mouse to ({x}, {y})."
    except Exception as e:
        return _err(f"mouse_move failed: {e}")


def mouse_click(x: int | None = None, y: int | None = None,
                button: str = "left", double: bool = False) -> str:
    if (g := _control_allowed()):
        return g
    pg = _pyautogui()
    if pg is None:
        return _need("pyautogui (mouse/keyboard control)", "pyautogui")
    try:
        kw = {"button": button}
        if x is not None and y is not None:
            kw.update(x=int(x), y=int(y))
        if double:
            pg.doubleClick(**kw)
        else:
            pg.click(**kw)
        where = f" at ({x}, {y})" if x is not None else ""
        return f"{'Double-' if double else ''}Clicked {button}{where}."
    except Exception as e:
        return _err(f"mouse_click failed: {e}")


def type_text(text: str) -> str:
    if (g := _control_allowed()):
        return g
    pg = _pyautogui()
    if pg is None:
        return _need("pyautogui (mouse/keyboard control)", "pyautogui")
    try:
        value = str(text)
        # pyautogui.typewrite is ASCII-only. Clipboard paste handles Unicode
        # (accented text, emoji, non-Latin scripts) on Windows/Linux desktops.
        if any(ord(ch) > 127 for ch in value):
            try:
                import pyperclip
                old = pyperclip.paste()
                pyperclip.copy(value)
                pg.hotkey("ctrl", "v")
                try: pyperclip.copy(old)
                except Exception: pass
            except Exception:
                pg.write(value, interval=0.01)
        else:
            pg.typewrite(value, interval=0.01)
        return f"Typed {len(value)} characters into the active window."
    except Exception as e:
        return _err(f"type_text failed: {e}")


def press_keys(keys: str) -> str:
    """Press a key or a combo. 'enter' | 'ctrl+c' | 'alt+tab' | 'win+r'."""
    if (g := _control_allowed()):
        return g
    pg = _pyautogui()
    if pg is None:
        return _need("pyautogui (mouse/keyboard control)", "pyautogui")
    try:
        combo = [k.strip().lower().replace("win", "winleft").replace("cmd", "command")
                 for k in str(keys).replace(" ", "").split("+") if k.strip()]
        if len(combo) > 1:
            pg.hotkey(*combo)
        elif combo:
            pg.press(combo[0])
        else:
            return _err("no keys given")
        return f"Pressed {keys}."
    except Exception as e:
        return _err(f"press_keys failed: {e}")


def scroll(amount: int = -400) -> str:
    if (g := _control_allowed()):
        return g
    pg = _pyautogui()
    if pg is None:
        return _need("pyautogui (mouse/keyboard control)", "pyautogui")
    try:
        pg.scroll(int(amount))
        return f"Scrolled {amount}."
    except Exception as e:
        return _err(f"scroll failed: {e}")


def screen_size() -> str:
    pg = _pyautogui()
    if pg is None:
        return _need("pyautogui", "pyautogui")
    try:
        w, h = pg.size()
        x, y = pg.position()
        return f"Screen size: {w}x{h}. Mouse at ({x}, {y})."
    except Exception as e:
        return _err(f"screen_size failed: {e}")


# --------------------------------------------------------------------------- #
# Pack 2 — System & power
# --------------------------------------------------------------------------- #
def list_processes(filter: str | None = None, limit: int = 25) -> str:
    ps = _optional("psutil")
    if ps is None:
        return _need("psutil", "psutil")
    rows = []
    for p in ps.process_iter(["pid", "name", "memory_info"]):
        try:
            nm = p.info["name"] or "?"
            if filter and filter.lower() not in nm.lower():
                continue
            mem = (p.info["memory_info"].rss / 1e6) if p.info["memory_info"] else 0
            rows.append((mem, p.info["pid"], nm))
        except Exception:
            continue
    rows.sort(reverse=True)
    if not rows:
        return f"No processes match '{filter}'." if filter else "No processes found."
    out = [f"{'PID':>7}  {'MEM(MB)':>8}  NAME"]
    for mem, pid, nm in rows[:limit]:
        out.append(f"{pid:>7}  {mem:>8.1f}  {nm}")
    return "\n".join(out)


def kill_process(name_or_pid: str, confirmed: bool = False) -> str:
    if config.AUTONOMY != "yolo" and not confirmed:
        return f"CONFIRM_REQUIRED: end process '{name_or_pid}'? Set confirmed=true to proceed."
    ps = _optional("psutil")
    if ps is None:
        return _need("psutil", "psutil")
    killed = []
    try:
        if str(name_or_pid).isdigit():
            p = ps.Process(int(name_or_pid)); p.terminate(); killed.append(f"{p.name()} ({p.pid})")
        else:
            for p in ps.process_iter(["pid", "name"]):
                if (p.info["name"] or "").lower() == str(name_or_pid).lower():
                    p.terminate(); killed.append(f"{p.info['name']} ({p.info['pid']})")
        if not killed:
            return _err(f"no process named '{name_or_pid}' found")
        return "Terminated: " + ", ".join(killed)
    except Exception as e:
        return _err(f"kill_process failed: {e}")


def media_key(action: str) -> str:
    """playpause | next | prev | mute | volup | voldown."""
    if (g := _control_allowed()):
        return g
    pg = _pyautogui()
    if pg is None:
        return _need("pyautogui", "pyautogui")
    mapping = {"playpause": "playpause", "play": "playpause", "pause": "playpause",
               "next": "nexttrack", "prev": "prevtrack", "previous": "prevtrack",
               "mute": "volumemute", "volup": "volumeup", "voldown": "volumedown"}
    key = mapping.get(str(action).lower())
    if not key:
        return _err(f"unknown media action '{action}'. Use playpause/next/prev/mute/volup/voldown.")
    try:
        pg.press(key)
        return f"Media: {action}."
    except Exception as e:
        return _err(f"media_key failed: {e}")


def set_volume(level: int) -> str:
    """Set master volume 0-100 (Windows: pycaw)."""
    level = max(0, min(100, int(level)))
    if IS_WINDOWS:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            dev = AudioUtilities.GetSpeakers()
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
            vol.SetMasterVolumeLevelScalar(level / 100.0, None)
            return f"Volume set to {level}%."
        except Exception:
            return _need("Windows volume control (pycaw)", "pycaw comtypes")
    # macOS
    if sys.platform == "darwin":
        os.system(f"osascript -e 'set volume output volume {level}'")
        return f"Volume set to {level}%."
    # Linux
    if shutil.which("amixer"):
        os.system(f"amixer -q sset Master {level}%")
        return f"Volume set to {level}%."
    return _err("no supported volume backend on this OS.")


def notify(title: str, message: str = "") -> str:
    """Show a desktop notification."""
    plyer = _optional("plyer")
    if plyer is not None:
        try:
            from plyer import notification as _n
            _n.notify(title=str(title), message=str(message), timeout=6)
            return "Notification shown."
        except Exception:
            pass
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(message), str(title), 0x40)
            return "Notification shown (message box)."
        except Exception as e:
            return _err(f"notify failed: {e}")
    if sys.platform == "darwin":
        os.system(f"osascript -e 'display notification \"{message}\" with title \"{title}\"'")
        return "Notification shown."
    if shutil.which("notify-send"):
        os.system(f'notify-send "{title}" "{message}"')
        return "Notification shown."
    return _err("no notification backend available (try: pip install plyer)")


def set_brightness(level: int) -> str:
    level = max(0, min(100, int(level)))
    if IS_WINDOWS:
        try:
            ps = (f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                  f".WmiSetBrightness(1,{level})")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, timeout=10)
            return f"Brightness set to {level}%."
        except Exception as e:
            return _err(f"set_brightness failed: {e}")
    return _err("set_brightness is currently Windows-only.")


def power_action(action: str, confirmed: bool = False) -> str:
    """lock | sleep | shutdown | restart. Everything but lock confirms first."""
    action = str(action).lower()
    if action not in {"lock", "sleep", "shutdown", "restart"}:
        return _err("action must be lock/sleep/shutdown/restart.")
    if action != "lock" and config.AUTONOMY != "yolo" and not confirmed:
        return f"CONFIRM_REQUIRED: {action} this computer? Set confirmed=true to proceed."
    try:
        if IS_WINDOWS:
            cmds = {
                "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
                "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                "shutdown": ["shutdown", "/s", "/t", "5"],
                "restart": ["shutdown", "/r", "/t", "5"],
            }
        elif sys.platform == "darwin":
            cmds = {
                "lock": ["pmset", "displaysleepnow"],
                "sleep": ["pmset", "sleepnow"],
                "shutdown": ["osascript", "-e", 'tell app "System Events" to shut down'],
                "restart": ["osascript", "-e", 'tell app "System Events" to restart'],
            }
        else:
            cmds = {
                "lock": ["loginctl", "lock-session"],
                "sleep": ["systemctl", "suspend"],
                "shutdown": ["shutdown", "-h", "now"],
                "restart": ["reboot"],
            }
        subprocess.Popen(cmds[action])
        return f"{action.capitalize()} initiated."
    except Exception as e:
        return _err(f"power_action failed: {e}")


# --------------------------------------------------------------------------- #
# Pack 3 — Documents & files
# --------------------------------------------------------------------------- #
def create_document(path: str, content: str, kind: str | None = None) -> str:
    """Create a real document. kind: docx | xlsx | pptx | pdf | txt | md (auto from ext)."""
    if not config.RUNTIME.get("fs_write", True):
        return _err("file writes are disabled (FS Write capability is off).")
    p = _resolve_in_workspace(path)
    if isinstance(p, str):
        return p
    kind = (kind or p.suffix.lstrip(".") or "txt").lower()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if kind in ("txt", "md"):
            p.write_text(content, encoding="utf-8")
        elif kind == "docx":
            docx = _optional("docx")
            if docx is None:
                return _need("python-docx", "python-docx")
            from docx import Document
            doc = Document()
            for para in content.split("\n"):
                if para.startswith("# "):
                    doc.add_heading(para[2:], 1)
                elif para.startswith("## "):
                    doc.add_heading(para[3:], 2)
                else:
                    doc.add_paragraph(para)
            doc.save(str(p))
        elif kind == "xlsx":
            opx = _optional("openpyxl")
            if opx is None:
                return _need("openpyxl", "openpyxl")
            from openpyxl import Workbook
            wb = Workbook(); ws = wb.active
            for line in content.strip().split("\n"):
                ws.append([c.strip() for c in line.split(",")])
            wb.save(str(p))
        elif kind == "pptx":
            pptx = _optional("pptx")
            if pptx is None:
                return _need("python-pptx", "python-pptx")
            from pptx import Presentation
            prs = Presentation()
            for block in content.split("\n---\n"):
                lines = [l for l in block.strip().split("\n") if l]
                slide = prs.slides.add_slide(prs.slide_layouts[1])
                if lines:
                    slide.shapes.title.text = lines[0]
                    body = slide.placeholders[1].text_frame
                    for l in lines[1:]:
                        body.add_paragraph().text = l
            prs.save(str(p))
        elif kind == "pdf":
            fpdf = _optional("fpdf")
            if fpdf is None:
                return _need("fpdf2 (PDF creation)", "fpdf2")
            from fpdf import FPDF
            pdf = FPDF(); pdf.add_page()
            pdf.set_auto_page_break(True, margin=15)
            pdf.set_font("Helvetica", size=12)
            for line in content.split("\n"):
                clean = line.encode("latin-1", "replace").decode("latin-1")
                if clean.strip() == "":
                    pdf.ln(8)
                else:
                    pdf.multi_cell(pdf.epw, 8, clean)
            pdf.output(str(p))
        else:
            return _err(f"unsupported document kind '{kind}'.")
        return f"Created {kind.upper()} document: {p}"
    except Exception as e:
        return _err(f"create_document failed: {e}")


def read_document(path: str, max_chars: int = 8000) -> str:
    """Extract text from a PDF, Word (.docx), or Excel (.xlsx) file."""
    p = _resolve_in_workspace(path)
    if isinstance(p, str):
        return p
    if not p.exists():
        return _err(f"no such file: {p}")
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            pypdf = _optional("pypdf")
            if pypdf is None:
                return _need("pypdf", "pypdf")
            from pypdf import PdfReader
            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
        elif ext == ".docx":
            docx = _optional("docx")
            if docx is None:
                return _need("python-docx", "python-docx")
            from docx import Document
            text = "\n".join(par.text for par in Document(str(p)).paragraphs)
        elif ext == ".xlsx":
            opx = _optional("openpyxl")
            if opx is None:
                return _need("openpyxl", "openpyxl")
            from openpyxl import load_workbook
            wb = load_workbook(str(p), read_only=True, data_only=True)
            rows = []
            for ws in wb.worksheets:
                rows.append(f"# {ws.title}")
                for r in ws.iter_rows(values_only=True):
                    rows.append(", ".join("" if c is None else str(c) for c in r))
            text = "\n".join(rows)
        elif ext in (".txt", ".md", ".csv", ".log", ".json"):
            text = p.read_text(encoding="utf-8", errors="replace")
        else:
            return _err(f"unsupported document type '{ext}'. Try read_file for plain text.")
        text = text.strip() or "(no extractable text)"
        return text[:max_chars] + ("\n…[truncated]" if len(text) > max_chars else "")
    except Exception as e:
        return _err(f"read_document failed: {e}")


def download_file(url: str, path: str | None = None) -> str:
    if not config.RUNTIME.get("web", True):
        return _err("outbound internet is disabled (Web capability is off).")
    if not config.RUNTIME.get("fs_write", True):
        return _err("file writes are disabled (FS Write capability is off).")
    try:
        if not path:
            name = os.path.basename(urlparse(url).path) or "download.bin"
            path = str(Path.home() / "Downloads" / name)
        p = _resolve_in_workspace(path)
        if isinstance(p, str):
            return p
        p.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(p, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        return f"Downloaded to {p} ({p.stat().st_size} bytes)."
    except Exception as e:
        return _err(f"download_file failed: {e}")


def zip_paths(paths: str, out: str) -> str:
    """Zip one or more paths (comma-separated) into `out`."""
    if not config.RUNTIME.get("fs_write", True):
        return _err("file writes are disabled (FS Write capability is off).")
    import zipfile
    outp = _resolve_in_workspace(out)
    if isinstance(outp, str):
        return outp
    try:
        with zipfile.ZipFile(outp, "w", zipfile.ZIP_DEFLATED) as z:
            for raw in [s.strip() for s in paths.split(",") if s.strip()]:
                src = _resolve_in_workspace(raw)
                if isinstance(src, str):
                    return src
                if src.is_dir():
                    for f in src.rglob("*"):
                        if f.is_file():
                            z.write(f, f.relative_to(src.parent))
                elif src.exists():
                    z.write(src, src.name)
        return f"Created archive {outp}."
    except Exception as e:
        return _err(f"zip_paths failed: {e}")


def unzip(path: str, dest: str | None = None) -> str:
    if not config.RUNTIME.get("fs_write", True):
        return _err("file writes are disabled (FS Write capability is off).")
    import zipfile
    src = _resolve_in_workspace(path)
    if isinstance(src, str):
        return src
    destp = _resolve_in_workspace(dest) if dest else src.with_suffix("")
    if isinstance(destp, str):
        return destp
    try:
        with zipfile.ZipFile(src) as z:
            z.extractall(destp)
        return f"Extracted to {destp}."
    except Exception as e:
        return _err(f"unzip failed: {e}")


# --------------------------------------------------------------------------- #
# Pack 4 — Automation & scheduling
# --------------------------------------------------------------------------- #
def schedule_task(instruction: str, run_in_minutes: int | None = None,
                  at: str | None = None, every_minutes: int | None = None) -> str:
    """Schedule an instruction for Sakura to run later or repeatedly.
    Provide run_in_minutes (delay), at ('HH:MM' today/tomorrow), or every_minutes (recurring)."""
    from core import scheduler
    return scheduler.add_task(instruction, run_in_minutes=run_in_minutes,
                              at=at, every_minutes=every_minutes)


def list_tasks() -> str:
    from core import scheduler
    return scheduler.list_tasks()


def cancel_task(task_id: str) -> str:
    from core import scheduler
    return scheduler.cancel_task(task_id)


# --------------------------------------------------------------------------- #
# Pack 5 — Browser automation (Playwright)
# --------------------------------------------------------------------------- #
def browser_open(url: str) -> str:
    if not config.RUNTIME.get("web", True):
        return _err("outbound internet is disabled (Web capability is off).")
    from core import browser
    return browser.open_page(url)


def browser_read() -> str:
    from core import browser
    return browser.read_text()


def browser_click(target: str) -> str:
    from core import browser
    return browser.click(target)


def browser_type(target: str, text: str, submit: bool = False) -> str:
    from core import browser
    return browser.type_into(target, text, submit)


def browser_screenshot(path: str | None = None) -> str:
    from core import browser
    return browser.shot(path)


# --------------------------------------------------------------------------- #
# Pack 6 — Smarter brain
# --------------------------------------------------------------------------- #
def analyze_image(path: str, question: str = "Describe this image in detail.") -> str:
    """Look at ANY image file (not just the screen) with the local vision model."""
    p = _resolve_in_workspace(path)
    if isinstance(p, str):
        return p
    if not p.exists():
        return _err(f"no such image: {p}")
    try:
        import base64
        from core import ollama_check
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        msg = ollama_check.chat(
            config.MODELS["vision"],
            [{"role": "user", "content": question}],
            images=[b64],
        )
        return (msg.get("content") or "").strip() or "(no answer)"
    except Exception as e:
        return _err(f"analyze_image failed: {e}")


def run_python(code: str, timeout: int = 30) -> str:
    """Execute a snippet of Python and return its stdout/stderr."""
    if not config.RUNTIME.get("shell", True):
        return _err("code execution is disabled (Shell capability is off).")
    try:
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
        return out.strip()[:6000] or "(no output)"
    except subprocess.TimeoutExpired:
        return _err(f"code timed out after {timeout}s")
    except Exception as e:
        return _err(f"run_python failed: {e}")


# --------------------------------------------------------------------------- #
# Registry + schema
# --------------------------------------------------------------------------- #
TOOL_FUNCTIONS: dict[str, Callable[..., str]] = {
    "list_dir": list_dir,
    "read_file": read_file,
    "write_file": write_file,
    "search_files": search_files,
    "run_command": run_command,
    "read_clipboard": read_clipboard,
    "write_clipboard": write_clipboard,
    "list_windows": list_windows,
    "focus_window": focus_window,
    "open_app": open_app,
    "open_path": open_path,
    "find_files": find_files,
    "delete_path": delete_path,
    "open_url": open_url,
    "web_search": web_search,
    "fetch_url": fetch_url,
    "screenshot": screenshot,
    "ocr_image": ocr_image,
    "send_email": send_email,
    "remember": remember,
    "recall_notes": recall_notes,
    "learn": learn,
    "skills": skills,
    "remember_document": remember_document,
    "search_knowledge": search_knowledge,
    "system_info": system_info,
    # Pack 1 — computer control
    "mouse_move": mouse_move,
    "mouse_click": mouse_click,
    "type_text": type_text,
    "press_keys": press_keys,
    "scroll": scroll,
    "screen_size": screen_size,
    # Pack 2 — system & power
    "list_processes": list_processes,
    "kill_process": kill_process,
    "media_key": media_key,
    "set_volume": set_volume,
    "notify": notify,
    "set_brightness": set_brightness,
    "power_action": power_action,
    # Pack 3 — documents & files
    "create_document": create_document,
    "read_document": read_document,
    "download_file": download_file,
    "zip_paths": zip_paths,
    "unzip": unzip,
    # Pack 4 — automation & scheduling
    "schedule_task": schedule_task,
    "list_tasks": list_tasks,
    "cancel_task": cancel_task,
    # Pack 5 — browser automation
    "browser_open": browser_open,
    "browser_read": browser_read,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_screenshot": browser_screenshot,
    # Pack 6 — smarter brain
    "analyze_image": analyze_image,
    "run_python": run_python,
}

# Which tools are read-only (run immediately, never gated).
READ_ONLY_TOOLS = {
    "list_dir", "read_file", "search_files", "read_clipboard", "list_windows",
    "web_search", "fetch_url", "screenshot", "ocr_image", "recall_notes",
    "search_knowledge", "system_info", "skills", "find_files",
    "screen_size", "list_processes", "read_document", "list_tasks",
    "browser_read", "analyze_image",
}


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_INT = {"type": "integer"}

TOOLS_SCHEMA: list[dict[str, Any]] = [
    _fn("list_dir", "List files in a directory.",
        {"path": {**_STR, "description": "Directory path. Defaults to '.'"}}, []),
    _fn("read_file", "Read a UTF-8 text file.",
        {"path": _STR}, ["path"]),
    _fn("write_file",
        "Write text to a file. If the path exists you MUST pass overwrite=true.",
        {"path": _STR, "content": _STR,
         "overwrite": {**_BOOL, "description": "Replace an existing file."}},
        ["path", "content"]),
    _fn("search_files", "Recursively find files matching a glob pattern.",
        {"pattern": {**_STR, "description": "Glob, e.g. '*.py'"}, "path": _STR},
        ["pattern"]),
    _fn("run_command",
        "Run a shell command and return its output. Risky commands need confirmed=true.",
        {"command": _STR,
         "confirmed": {**_BOOL, "description": "Set true only after the user confirms."}},
        ["command"]),
    _fn("read_clipboard", "Read the system clipboard.", {}, []),
    _fn("write_clipboard", "Put text on the system clipboard.",
        {"text": _STR}, ["text"]),
    _fn("list_windows", "List open application window titles (Windows).", {}, []),
    _fn("focus_window", "Bring a window to the foreground by title match (Windows).",
        {"title": _STR}, ["title"]),
    _fn("open_app",
        "Open/launch an application by NAME (e.g. 'Roblox', 'Spotify', 'Chrome') or "
        "open a file/folder/URL. Use this to open anything the user asks for.",
        {"name_or_path": _STR}, ["name_or_path"]),
    _fn("open_path", "Open a file with its default app, or open a folder.",
        {"path": _STR}, ["path"]),
    _fn("find_files",
        "Find files by name or glob under the user's folders (Desktop, Documents, "
        "Downloads, etc.) or a given root. Use before opening/deleting a file you must locate.",
        {"query": {**_STR, "description": "filename text or glob like '*.pdf'"},
         "root": {**_STR, "description": "optional folder to search under"}},
        ["query"]),
    _fn("delete_path",
        "Delete a file or folder permanently. Confirms first unless in Unleashed mode.",
        {"path": _STR, "confirmed": _BOOL}, ["path"]),
    _fn("open_url", "Open a URL in the default web browser.",
        {"url": _STR}, ["url"]),
    _fn("web_search",
        "Search the web (DuckDuckGo) for current or unknown info. Returns ranked "
        "titles, URLs, and snippets. Use this before answering anything time-sensitive.",
        {"query": _STR,
         "max_results": {"type": "integer", "description": "Default 5."}},
        ["query"]),
    _fn("fetch_url",
        "Fetch a web page and return extracted text (no JS). Use after web_search "
        "to read a specific result in full.",
        {"url": _STR}, ["url"]),
    _fn("screenshot", "Capture the screen to a PNG; returns the file path.",
        {"path": {**_STR, "description": "Optional output path."}}, []),
    _fn("ocr_image", "Extract text from an image file via Tesseract.",
        {"path": _STR}, ["path"]),
    _fn("send_email",
        "Send an email. Always requires confirmed=true after the user agrees.",
        {"to": _STR, "subject": _STR, "body": _STR,
         "confirmed": _BOOL}, ["to", "subject", "body"]),
    _fn("remember", "Save a durable note/fact for future sessions.",
        {"note": _STR}, ["note"]),
    _fn("recall_notes", "List all saved notes.", {}, []),
    _fn("learn",
        "Teach yourself a reusable skill/procedure so you can repeat it later. "
        "Give it a short name and the steps/how-to as content.",
        {"name": _STR, "content": _STR}, ["name", "content"]),
    _fn("skills", "List the skills you have taught yourself.", {}, []),
    _fn("remember_document",
        "Index a text file into the local knowledge base for later search.",
        {"path": _STR}, ["path"]),
    _fn("search_knowledge", "Semantic-search the local knowledge base.",
        {"query": _STR}, ["query"]),
    _fn("system_info", "Report OS, Python, CPU, and current safety settings.", {}, []),

    # ---- Pack 1: computer control (mouse + keyboard) ----
    _fn("mouse_move", "Move the mouse cursor to screen pixel (x, y).",
        {"x": _INT, "y": _INT}, ["x", "y"]),
    _fn("mouse_click",
        "Click the mouse. Optionally at (x, y). button=left/right/middle; double=true for double-click.",
        {"x": _INT, "y": _INT, "button": _STR, "double": _BOOL}, []),
    _fn("type_text", "Type text into whatever window is focused (like a keyboard).",
        {"text": _STR}, ["text"]),
    _fn("press_keys",
        "Press a key or combo, e.g. 'enter', 'ctrl+c', 'alt+tab', 'win+r'.",
        {"keys": _STR}, ["keys"]),
    _fn("scroll", "Scroll the mouse wheel. Negative scrolls down, positive up.",
        {"amount": _INT}, []),
    _fn("screen_size", "Report screen resolution and current mouse position.", {}, []),

    # ---- Pack 2: system & power ----
    _fn("list_processes", "List running processes (by memory). Optional name filter.",
        {"filter": {**_STR, "description": "substring to match process names"},
         "limit": _INT}, []),
    _fn("kill_process",
        "End a process by name or PID. Confirms first unless in Unleashed mode.",
        {"name_or_pid": _STR, "confirmed": _BOOL}, ["name_or_pid"]),
    _fn("media_key",
        "Media/volume key: playpause | next | prev | mute | volup | voldown.",
        {"action": _STR}, ["action"]),
    _fn("set_volume", "Set the master volume to a level from 0 to 100.",
        {"level": _INT}, ["level"]),
    _fn("notify", "Show a desktop notification to the user.",
        {"title": _STR, "message": _STR}, ["title"]),
    _fn("set_brightness", "Set screen brightness 0-100 (Windows).",
        {"level": _INT}, ["level"]),
    _fn("power_action",
        "Power control: lock | sleep | shutdown | restart. Confirms first (except lock).",
        {"action": _STR, "confirmed": _BOOL}, ["action"]),

    # ---- Pack 3: documents & files ----
    _fn("create_document",
        "Create a real document. kind = docx | xlsx | pptx | pdf | txt | md (auto from "
        "extension). For xlsx use comma-separated rows; for pptx separate slides with a line '---'.",
        {"path": _STR, "content": _STR, "kind": _STR}, ["path", "content"]),
    _fn("read_document",
        "Extract text from a PDF, Word (.docx) or Excel (.xlsx) file so you can read it.",
        {"path": _STR}, ["path"]),
    _fn("download_file", "Download a file from a URL (defaults to the Downloads folder).",
        {"url": _STR, "path": {**_STR, "description": "optional save path"}}, ["url"]),
    _fn("zip_paths", "Zip one or more paths (comma-separated) into an archive.",
        {"paths": _STR, "out": _STR}, ["paths", "out"]),
    _fn("unzip", "Extract a .zip archive.",
        {"path": _STR, "dest": {**_STR, "description": "optional destination folder"}}, ["path"]),

    # ---- Pack 4: automation & scheduling ----
    _fn("schedule_task",
        "Schedule an instruction for you to run later or repeatedly. Give run_in_minutes "
        "(a delay), at ('HH:MM'), or every_minutes (recurring).",
        {"instruction": _STR, "run_in_minutes": _INT, "at": _STR, "every_minutes": _INT},
        ["instruction"]),
    _fn("list_tasks", "List scheduled tasks.", {}, []),
    _fn("cancel_task", "Cancel a scheduled task by its id.",
        {"task_id": _STR}, ["task_id"]),

    # ---- Pack 5: browser automation ----
    _fn("browser_open",
        "Open a real automated browser at a URL and return the page's text (handles JS/logins).",
        {"url": _STR}, ["url"]),
    _fn("browser_read", "Read the current automated-browser page text.", {}, []),
    _fn("browser_click", "Click an element in the automated browser by visible text or CSS selector.",
        {"target": _STR}, ["target"]),
    _fn("browser_type",
        "Type into a field in the automated browser (by CSS selector or placeholder). submit=true to press Enter.",
        {"target": _STR, "text": _STR, "submit": _BOOL}, ["target", "text"]),
    _fn("browser_screenshot", "Screenshot the automated browser page to a PNG.",
        {"path": _STR}, []),

    # ---- Pack 6: smarter brain ----
    _fn("analyze_image",
        "Look at ANY image file with the local vision model and answer a question about it.",
        {"path": _STR, "question": _STR}, ["path"]),
    _fn("run_python",
        "Execute a snippet of Python and return its output. Good for math, data, quick logic.",
        {"code": _STR, "timeout": _INT}, ["code"]),
]
