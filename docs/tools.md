# Tools (capabilities)

Everything the model can *do* lives in `tools/tools.py`. Each tool is a plain Python
function that returns a **string** (what the model sees as the result). Three structures
tie it together:

- `TOOL_FUNCTIONS` — `name → function` dispatch table the agent calls.
- `TOOLS_SCHEMA` — the JSON schema list handed to Ollama so the model knows the tools.
- `READ_ONLY_TOOLS` — the set that runs immediately, never gated.

## Catalog

| Tool | Args | Gated? | What it does |
|---|---|---|---|
| `list_dir` | `path` | read-only | List a directory |
| `read_file` | `path`, `max_bytes` | read-only | Read a UTF-8 text file |
| `write_file` | `path`, `content`, `overwrite` | write | Write a file; existing path needs `overwrite=true` |
| `search_files` | `pattern`, `path` | read-only | Recursive glob search |
| `run_command` | `command`, `confirmed` | **risky → confirm** | Run a shell command (120s cap) |
| `read_clipboard` | — | read-only | Read the clipboard |
| `write_clipboard` | `text` | write | Set the clipboard |
| `list_windows` | — | read-only | List window titles (Windows) |
| `focus_window` | `title` | action | Focus a window by title (Windows) |
| `open_app` | `name_or_path` | action | Launch an app by **name** (e.g. `Roblox`, `Spotify`), or open a file/folder/URL. On Windows it resolves Store/desktop apps via `Get-StartApps`, `start`, `where`, then Start-Menu shortcuts |
| `open_path` | `path` | action | Open a specific file in its default app, or open a folder |
| `find_files` | `query`, `root` | read-only | Find files by name or glob under the user's folders (Desktop/Documents/Downloads/…) or a given `root`; bounded (12s, capped results) and skips system dirs |
| `delete_path` | `path`, `confirmed` | **risky → confirm** | Delete a file or folder; asks once unless in Unleashed mode |
| `open_url` | `url` | action | Open a URL in the browser |
| `web_search` | `query`, `max_results` | read-only | Search the web (DuckDuckGo, no API key); ranked title/URL/snippet |
| `fetch_url` | `url`, `max_chars` | read-only | Fetch a page, return extracted text (no JS) |
| `screenshot` | `path` | read-only | Capture the screen to PNG |
| `ocr_image` | `path` | read-only | Extract text via Tesseract |
| `send_email` | `to`, `subject`, `body`, `confirmed` | **always confirm** | Send email over SMTP |
| `remember` | `note` | write | Save a durable fact |
| `recall_notes` | — | read-only | List saved notes |
| `learn` | `name`, `content` | write | Teach itself a reusable skill/procedure |
| `skills` | — | read-only | List self-taught skills |
| `remember_document` | `path` | write | Index a text file into RAG |
| `search_knowledge` | `query` | read-only | Semantic search over indexed docs |
| `system_info` | — | read-only | OS/Python/CPU + current safety settings |
| **— Computer control —** | | | |
| `mouse_move` | `x`, `y` | action | Move the cursor to a pixel |
| `mouse_click` | `x?`, `y?`, `button`, `double` | action | Click (optionally at a point) |
| `type_text` | `text` | action | Type into the focused window |
| `press_keys` | `keys` | action | Press a key/combo (`ctrl+c`, `alt+tab`, `win+r`) |
| `scroll` | `amount` | action | Scroll the mouse wheel |
| `screen_size` | — | read-only | Resolution + cursor position |
| **— System & power —** | | | |
| `list_processes` | `filter?`, `limit` | read-only | Running processes by memory |
| `kill_process` | `name_or_pid`, `confirmed` | **risky → confirm** | End a process |
| `media_key` | `action` | action | playpause/next/prev/mute/volup/voldown |
| `set_volume` | `level` | action | Master volume 0-100 (Win: pycaw) |
| `notify` | `title`, `message` | action | Desktop notification |
| `set_brightness` | `level` | action | Screen brightness 0-100 (Windows) |
| `power_action` | `action`, `confirmed` | **risky → confirm** (lock is free) | lock/sleep/shutdown/restart |
| **— Documents & files —** | | | |
| `create_document` | `path`, `content`, `kind` | write | Create Word/Excel/PPT/PDF/txt/md |
| `read_document` | `path` | read-only | Extract text from PDF/Word/Excel |
| `download_file` | `url`, `path?` | write + net | Download a file (defaults to Downloads) |
| `zip_paths` | `paths`, `out` | write | Zip files/folders |
| `unzip` | `path`, `dest?` | write | Extract a .zip |
| **— Automation —** | | | |
| `schedule_task` | `instruction`, `run_in_minutes?`, `at?`, `every_minutes?` | write | Run an instruction later/recurring |
| `list_tasks` | — | read-only | List scheduled tasks |
| `cancel_task` | `task_id` | write | Cancel a scheduled task |
| **— Browser automation —** | | | |
| `browser_open` | `url` | net | Open a real (Playwright) browser page, return text |
| `browser_read` | — | read-only | Read the current page text |
| `browser_click` | `target` | net | Click by visible text or CSS selector |
| `browser_type` | `target`, `text`, `submit` | net | Fill a field (optionally submit) |
| `browser_screenshot` | `path?` | action | Screenshot the browser page |
| **— Smarter brain —** | | | |
| `analyze_image` | `path`, `question` | read-only | Vision Q&A on any image file |
| `run_python` | `code`, `timeout` | action (needs Shell) | Execute a Python snippet |

Windows-only tools (`list_windows`, `focus_window`) return a friendly error on other
platforms rather than crashing.

## The confirmation contract

Gated tools support a `confirmed` argument. When the model calls one without it, the
function returns a string starting `CONFIRM_REQUIRED:` **and** the agent's `_check_gate`
intercepts it, pausing the turn and surfacing a `needs_confirmation` payload to the UI.
After the human approves, the agent re-runs the call with `confirmed=true`.

- `run_command` is gated only when `is_risky_command()` matches (see `_RISKY_TOKENS`) and
  `AUTONOMY != "yolo"`.
- `delete_path` is gated whenever `AUTONOMY != "yolo"` — deleting files always asks once.
- `send_email` is **always** gated, regardless of autonomy.

## Adding your own tool

```python
# 1) write the function (return a string; catch your own errors)
def weather(city: str) -> str:
    r = requests.get(f"https://wttr.in/{city}?format=3", timeout=10)
    return r.text.strip() if r.ok else _err(r.status_code)

# 2) describe it for the model
_fn("weather", "Get current weather for a city.",
    {"city": {"type": "string"}}, ["city"])   # append to TOOLS_SCHEMA

# 3) register it
TOOL_FUNCTIONS["weather"] = weather
# (optional) READ_ONLY_TOOLS.add("weather")
```

The model can use it on the next run — **no change to `core/agent.py`**.

## Conventions

- **Return strings, not exceptions.** Prefix failures with `ERROR:` so the model can
  react and the loop keeps going.
- **Respect the workspace lock.** File tools call `_resolve_in_workspace()`, which refuses
  paths outside `WORKSPACE_ROOT` when it's set.
- **Keep results compact.** Long outputs are truncated (files at `max_bytes`, command
  output at ~8KB) so you don't blow the model's context window.
