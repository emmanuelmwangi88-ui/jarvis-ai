"""
Terminal-only JARVIS — no UI, no server. Same brain, same tools, same safety gates.

  python cli.py

Type your message and hit Enter. Commands:
  /reflect   force a reflect-and-remember pass
  /reset     clear conversation history
  /status    show Ollama connection + models
  /quit      exit (runs a final reflection)
"""
from __future__ import annotations

import sys

from core import agent, config, memory, ollama_check, rag


def _print_event(kind: str, data: dict) -> None:
    if kind == "route":
        print(f"  · routing to {data['role']} ({data['model']})", file=sys.stderr)
    elif kind == "tool":
        print(f"  · tool: {data['name']}({data.get('args', {})})", file=sys.stderr)
    elif kind == "reflect":
        print("  · reflecting…", file=sys.stderr)


def _confirm_prompt(message: str) -> bool:
    print("\n\033[33m" + message + "\033[0m")
    return input("Confirm? [yes/no] ").strip().lower() in ("y", "yes")


def main() -> int:
    config.ensure_dirs()
    memory.init()
    rag.init()

    try:
        ollama_check.start_server()
    except ollama_check.OllamaError as e:
        print(f"! {e}")
        return 1

    missing = ollama_check.missing_models()
    if missing:
        print("Missing models:", ", ".join(missing))
    print("JARVIS CLI ready. Type a message, or /quit to exit.\n")

    while True:
        try:
            text = input("\033[36myou›\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/reset":
            memory.clear_history()
            print("History cleared.")
            continue
        if text == "/reflect":
            print(agent.reflect_and_remember(_print_event))
            continue
        if text == "/status":
            st = ollama_check.status()
            print(f"connected={st['connected']} ready={st['ready']} missing={st['missing']}")
            continue

        result = agent.handle_message(text, on_event=_print_event)

        # Resolve any confirmation gate interactively.
        while result.needs_confirmation and not result.needs_confirmation.get("declined"):
            ok = _confirm_prompt(result.needs_confirmation["message"])
            result = agent.handle_message(text, confirm=ok, on_event=_print_event)

        print(f"\n\033[32mjarvis›\033[0m {result.reply}\n")

    print("Reflecting before exit…")
    print(agent.reflect_and_remember())
    print("Bye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
