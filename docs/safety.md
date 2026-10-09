# Safety model

Sakura AI can touch your real machine, so the defaults are conservative. Four mechanisms:

## 1. Read-only vs. gated tools
Read-only tools (search, read, list, fetch, screenshot, OCR, recall, system info) run
immediately — they can't damage anything. Tools that change state are subject to gates.

## 2. Confirmation gates
- **Risky terminal commands.** Before running anything matching `_RISKY_TOKENS`
  (`rm`, `del`, `format`, `dd`, `shutdown`, `sudo`, `git reset --hard`, …), the agent gets
  a quick **second opinion from `llama3.2:1b`** — what the command does and whether it
  risks data loss — and shows it next to the command. You approve or decline.
- **Deleting files/folders (`delete_path`) is gated** whenever `AUTONOMY != "yolo"`: the
  tool returns `CONFIRM_REQUIRED:` and the agent surfaces an authorize/deny card before
  anything is removed. In Unleashed it deletes without asking.
- **Sending email is always confirmed**, no matter the autonomy setting.
- **File overwrites** require the model to pass `overwrite=true`; a first write to an
  existing path is refused.

Mechanically: the tool returns `CONFIRM_REQUIRED:` and `agent._check_gate` pauses the
turn, returning a `needs_confirmation` payload. The human answers via the UI card (or the
CLI prompt), and the agent re-runs the call with `confirmed=true`.

## 3. Autonomy levels (`config.AUTONOMY`)
| Level | Behavior |
|---|---|
| `safe` (default) | risky commands are gated; email always gated |
| `yolo` | skips the risky-command gate (**not recommended**); email *still* gated |

Set via `SAKURA_AUTONOMY` (or legacy `JARVIS_AUTONOMY`) env var or edit `config.py`.

### Autonomy profiles (one-click in the UI)
`POST /api/autonomy` (or the segmented control in Sakura AI) applies a profile:
| Profile | Shell | Files | Web | Destructive cmds | Email |
|---|---|---|---|---|---|
| **Locked** | off | off | on | n/a | confirm |
| **Trusted** (default) | on | on | on | **confirm once** (incl. deletes) | confirm |
| **Unleashed** | on | on | on | **run without asking** (incl. deletes) | confirm |

Unleashed sets `AUTONOMY=yolo`. The UI shows a warning dialog before engaging it — it
lets the agent run *any* command on your machine unattended. Email is confirmed even in
Unleashed.

## 3b. Agent Sandbox toggles (live-enforced)
The four switches in the UI's **Agent Sandbox** panel map to `config.RUNTIME` and are
enforced *inside the tools*, not just visually:
| Toggle | When off, blocks |
|---|---|
| Shell Execution | `run_command` |
| FS Read/Write | `write_file` (and clipboard writes) |
| Outbound Internet | `web_search`, `fetch_url`, `open_url` |
| Audio Output | spoken voice replies |

Flipping a toggle calls `POST /api/settings`; the very next tool call respects it. This is
a real capability gate, so you can, e.g., cut off internet mid-session with one click.

## 4. Workspace lock (`config.WORKSPACE_ROOT`)
Point it at a folder to confine **all file tools** (`read_file`, `write_file`,
`list_dir`, `search_files`, `find_files`, `open_path`, `delete_path`) to that tree. Any
path that resolves outside is refused with
an error. `None` (default) = unrestricted — set it to cap the blast radius of a mistake.

## What "local" guarantees — and what it doesn't
- **Inference is local.** Prompts and replies go only to your Ollama server. Voice audio
  goes only to your local backend for transcription.
- **But tools reach out when you ask them to.** `fetch_url`/`open_url` hit the internet;
  `send_email` contacts your SMTP server. Those are explicit, gated where risky, and
  visible in the tool-call trace.
- **No telemetry.** Nothing phones home. History and notes stay in `~/.jarvis/`.

## Honest limitation: "plan before acting" is a prompt, not a lock
The system prompt tells the model to plan first, but nothing in code *forces* it to.
The model usually complies. The gates above are the real, code-enforced guardrails — they
hold regardless of what the model decides to do.
