"""
The brain: handle_message() runs the route -> chat -> (tool calls) -> chat loop,
persists history, applies safety gates, and periodically reflects.

The public surface is intentionally small:

    handle_message(user_text, confirm=None, on_event=None) -> AgentResult

`confirm` carries a human's yes/no back into a pending risky action. `on_event`
is an optional callback for streaming UI status ("thinking", "calling tool X"...).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from core import config, memory, model_router, ollama_check
from tools import tools as toolmod

EventCb = Callable[[str, dict[str, Any]], None]

MAX_TOOL_ITERATIONS = 6


@dataclass
class AgentResult:
    reply: str
    role: str                       # which model role handled it
    model: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    needs_confirmation: dict[str, Any] | None = None  # a gated action awaiting yes


def _emit(cb: EventCb | None, kind: str, **data: Any) -> None:
    if cb:
        try:
            cb(kind, data)
        except Exception:
            pass


# Category-specific "expert mode" guidance. After the router classifies a message,
# we append the matching block so each kind of task gets specialised instructions —
# this is what makes Sakura's answers sharper than a one-size-fits-all prompt.
_EXPERT_PROMPTS: dict[str, str] = {
    "code": (
        "## Mode: CODE\n"
        "You are in expert software-engineer mode. Write complete, correct, runnable "
        "code — no '...' placeholders. Include imports, error handling and edge cases. "
        "Prefer the language/framework the user is already using. After writing code to "
        "a file, verify it (compile/run/test) before claiming it works. Explain only "
        "what's non-obvious, in a short note after the code."
    ),
    "research": (
        "## Mode: RESEARCH\n"
        "You are in research mode. Do NOT answer from memory for anything current or "
        "factual — call web_search first, then fetch_url the best sources, and base the "
        "answer on what you actually read. Synthesize across sources, note disagreements, "
        "and cite each claim with its URL. Be concrete with numbers, dates and versions."
    ),
    "reason": (
        "## Mode: REASONING\n"
        "You are in deep-reasoning mode. Think step by step internally, then give a "
        "well-structured answer: state the conclusion first, then the key reasons. "
        "Surface assumptions and trade-offs. Use headings, short paragraphs and lists."
    ),
    "tools": (
        "## Mode: ACTIONS\n"
        "You are in operator mode, acting on the user's real machine. Take the action "
        "with tools rather than describing it. Chain tools and verify each result before "
        "the next step. Report exactly what you did and what changed."
    ),
    "vision": (
        "## Mode: VISION\n"
        "Describe what is actually visible, precisely. Don't guess beyond the image."
    ),
}


def _build_system(role: str = "chat") -> dict[str, str]:
    parts = [config.SYSTEM_PROMPT]
    expert = _EXPERT_PROMPTS.get(role)
    if expert:
        parts.append(expert)
    notes = memory.notes_as_context()
    if notes:
        parts.append(notes)
    skills = memory.skills_as_context()
    if skills:
        parts.append(skills)
    return {"role": "system", "content": "\n\n".join(parts)}


def _review_risky(command: str) -> str:
    """Ask the review model for a quick second opinion on a risky command."""
    prompt = (
        "In 2-3 sentences, say what this shell command does and whether it risks "
        f"data loss. Be blunt.\n\nCommand:\n{command}"
    )
    try:
        msg = ollama_check.chat(
            config.MODELS["review"],
            [{"role": "user", "content": prompt}],
            options={"temperature": 0.2, "num_predict": 160},
        )
        return (msg.get("content") or "").strip()
    except ollama_check.OllamaError as e:
        return f"(couldn't review: {e})"


def _run_tool(name: str, args: dict[str, Any]) -> str:
    fn = toolmod.TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"ERROR: unknown tool '{name}'."
    try:
        return fn(**args)
    except TypeError as e:
        return f"ERROR: bad arguments for {name}: {e}"
    except Exception as e:  # never let a tool crash the loop
        return f"ERROR: {name} raised {type(e).__name__}: {e}"


def _vision_answer(user_text: str, on_event: EventCb | None) -> AgentResult:
    """Direct vision call: take a screenshot and ask the vision model about it."""
    _emit(on_event, "tool", name="screenshot", args={})
    shot = toolmod.screenshot()
    if shot.startswith("ERROR"):
        return AgentResult(reply=shot, role="vision", model=config.MODELS["vision"])
    import base64
    from pathlib import Path

    b64 = base64.b64encode(Path(shot).read_bytes()).decode("ascii")
    _emit(on_event, "thinking", model=config.MODELS["vision"])
    msg = ollama_check.chat(
        config.MODELS["vision"],
        [{"role": "user", "content": user_text or "Describe what's on the screen."}],
        images=[b64],
    )
    reply = (msg.get("content") or "").strip() or "(no answer)"
    return AgentResult(
        reply=reply, role="vision", model=config.MODELS["vision"],
        tool_calls=[{"name": "screenshot", "result": shot}],
    )


def handle_message(
    user_text: str,
    confirm: bool | None = None,
    on_event: EventCb | None = None,
) -> AgentResult:
    """
    Process one user message end-to-end.

    If a previous call returned needs_confirmation, call again with the SAME
    user_text and confirm=True/False to resolve it.
    """
    memory.init()

    role, model, wants_tools = model_router.route(user_text)
    _emit(on_event, "route", role=role, model=model, label=model_router.label(role))

    # Screen questions bypass the tool loop entirely.
    if role == "vision":
        memory.add_message("user", user_text)
        result = _vision_answer(user_text, on_event)
        memory.add_message("assistant", result.reply, model=result.model)
        _maybe_reflect(on_event)
        return result

    # Assemble the conversation.
    messages: list[dict[str, Any]] = [_build_system(role)]
    messages.extend(memory.recent_messages(limit=config.HISTORY_LIMIT))
    user_msg: dict[str, Any] = {"role": "user", "content": user_text}
    if images:
        user_msg["images"] = [x.split(",", 1)[1] if "," in x else x for x in images[:4]]
    messages.append(user_msg)
    memory.add_message("user", user_text + (" [image attached]" if images else ""))

    tools_arg = toolmod.TOOLS_SCHEMA if wants_tools else None
    collected_calls: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        _emit(on_event, "thinking", model=model)
        try:
            msg = ollama_check.chat(model, messages, tools=tools_arg)
        except ollama_check.OllamaError as e:
            reply = f"I couldn't reach the model: {e}"
            memory.add_message("assistant", reply, model=model)
            return AgentResult(reply=reply, role=role, model=model)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            reply = (msg.get("content") or "").strip() or "(no reply)"
            memory.add_message("assistant", reply, model=model)
            _maybe_reflect(on_event)
            return AgentResult(
                reply=reply, role=role, model=model, tool_calls=collected_calls
            )

        # Record the assistant's tool-call turn so the model keeps context.
        messages.append(msg)

        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            args = _coerce_args(raw_args)

            gate = _check_gate(name, args, confirm)
            if gate is not None:
                # Pause and ask the human. State needed to resume is returned.
                return AgentResult(
                    reply=gate["message"],
                    role=role, model=model, tool_calls=collected_calls,
                    needs_confirmation=gate,
                )

            _emit(on_event, "tool", name=name, args=args)
            result = _run_tool(name, args)
            collected_calls.append({"name": name, "args": args, "result": result})
            messages.append({"role": "tool", "content": result})
        # loop again so the model can use the tool results
        confirm = None  # confirmation only applies to the first gated call

    # Ran out of iterations.
    reply = "I hit my tool-use limit for this turn. Here's where I got to — ask me to continue."
    memory.add_message("assistant", reply, model=model)
    return AgentResult(reply=reply, role=role, model=model, tool_calls=collected_calls)


def _coerce_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _check_gate(name: str, args: dict[str, Any], confirm: bool | None) -> dict[str, Any] | None:
    """
    Decide whether this tool call must pause for human confirmation.
    Returns None to proceed, or a dict describing the pending action.
    """
    # Email always confirms (unless the human already said yes this turn).
    if name == "send_email" and not args.get("confirmed"):
        if confirm is True:
            args["confirmed"] = True
            return None
        if confirm is False:
            return {
                "action": name, "args": args,
                "message": "Okay, I won't send that email.",
                "declined": True,
            }
        return {
            "action": name, "args": args, "review": "",
            "message": (
                f"About to send email to {args.get('to','?')} "
                f"(subject: {args.get('subject','')!r}). Confirm to proceed."
            ),
        }

    # Deleting files/folders always confirms unless autonomy is yolo.
    if name == "delete_path" and not args.get("confirmed"):
        if config.AUTONOMY != "yolo":
            if confirm is True:
                args["confirmed"] = True
                return None
            if confirm is False:
                return {"action": name, "args": args,
                        "message": "Okay, I won't delete that.", "declined": True}
            return {
                "action": name, "args": args, "review": "",
                "message": (
                    f"About to permanently delete:\n\n    {args.get('path','?')}\n\n"
                    "This cannot be undone. Confirm to proceed."
                ),
            }

    # Risky terminal commands confirm unless autonomy is yolo.
    if name == "run_command":
        cmd = args.get("command", "")
        if toolmod.is_risky_command(cmd) and config.AUTONOMY != "yolo" and not args.get("confirmed"):
            if confirm is True:
                args["confirmed"] = True
                return None
            if confirm is False:
                return {
                    "action": name, "args": args,
                    "message": "Understood, skipping that command.",
                    "declined": True,
                }
            review = _review_risky(cmd)
            return {
                "action": name, "args": args, "review": review,
                "message": (
                    f"This command looks risky:\n\n    {cmd}\n\n"
                    f"Second opinion ({config.MODELS['review']}): {review}\n\n"
                    "Confirm to run it."
                ),
            }

    # Other explicitly destructive tools use the same confirmed-arg convention.
    _skip = name == "power_action" and args.get("action") == "lock"
    if name in _GENERIC_CONFIRM and not args.get("confirmed") and not _skip:
        if config.AUTONOMY != "yolo":
            if confirm is True:
                args["confirmed"] = True
                return None
            if confirm is False:
                return {"action": name, "args": args,
                        "message": "Okay, cancelled.", "declined": True}
            return {
                "action": name, "args": args, "review": "",
                "message": _GENERIC_CONFIRM[name](args),
            }
    return None


# Destructive tools that must confirm once (unless autonomy is yolo).
_GENERIC_CONFIRM = {
    "kill_process": lambda a: f"About to end process '{a.get('name_or_pid','?')}'. Confirm to proceed.",
    "power_action": lambda a: (
        f"About to {a.get('action','?')} this computer. Confirm to proceed."
        if a.get("action") != "lock" else "Confirm locking the computer."
    ),
}


# --------------------------------------------------------------------------- #
# Streaming variant — yields events so the UI can render tokens as they arrive.
# --------------------------------------------------------------------------- #
def handle_message_stream(
    user_text: str,
    confirm: bool | None = None,
    images: list[str] | None = None,
):
    """
    Generator version of handle_message. Yields event dicts:
        {"t":"route", "role","model"}
        {"t":"token", "d": <text delta>}
        {"t":"tool",  "name","args","result"}
        {"t":"confirm","info": <gate dict>}
        {"t":"done",  "role","model","reply","tool_calls":[...]}
        {"t":"error", "message"}
    On a confirmation pause, re-invoke with the same user_text and confirm=True/False.
    """
    memory.init()
    role, model, wants_tools = model_router.route(user_text)
    yield {"t": "route", "role": role, "model": model, "label": model_router.label(role)}

    if role == "vision":
        memory.add_message("user", user_text)
        result = _vision_answer(user_text, None)
        for ch in result.reply:
            yield {"t": "token", "d": ch}
        memory.add_message("assistant", result.reply, model=result.model)
        _maybe_reflect(None)
        yield {"t": "done", "role": role, "model": result.model,
               "reply": result.reply, "tool_calls": result.tool_calls}
        return

    messages: list[dict[str, Any]] = [_build_system(role)]
    messages.extend(memory.recent_messages(limit=config.HISTORY_LIMIT))
    messages.append({"role": "user", "content": user_text})
    memory.add_message("user", user_text)

    tools_arg = toolmod.TOOLS_SCHEMA if wants_tools else None
    collected: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        acc = ""
        tool_calls: list[dict[str, Any]] = []
        try:
            for chunk in ollama_check.chat_stream(model, messages, tools=tools_arg):
                if chunk.get("tool_calls"):
                    tool_calls = chunk["tool_calls"]
                delta = chunk.get("content") or ""
                if delta and not tool_calls:
                    acc += delta
                    yield {"t": "token", "d": delta}
        except ollama_check.OllamaError as e:
            yield {"t": "error", "message": f"I couldn't reach the model: {e}"}
            return

        if not tool_calls:
            reply = acc.strip() or "(no reply)"
            memory.add_message("assistant", reply, model=model)
            _maybe_reflect(None)
            yield {"t": "done", "role": role, "model": model,
                   "reply": reply, "tool_calls": collected}
            return

        # model wants to use tools
        messages.append({"role": "assistant", "content": acc, "tool_calls": tool_calls})
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            args = _coerce_args(fn.get("arguments", {}))

            gate = _check_gate(name, args, confirm)
            if gate is not None:
                if gate.get("declined"):
                    yield {"t": "token", "d": gate["message"]}
                    memory.add_message("assistant", gate["message"], model=model)
                    yield {"t": "done", "role": role, "model": model,
                           "reply": gate["message"], "tool_calls": collected}
                    return
                yield {"t": "confirm", "info": gate}
                return

            result = _run_tool(name, args)
            collected.append({"name": name, "args": args, "result": result})
            yield {"t": "tool", "name": name, "args": args, "result": result}
            messages.append({"role": "tool", "content": result})
        confirm = None

    msg = "I hit my tool-use limit for this turn — ask me to continue."
    memory.add_message("assistant", msg, model=model)
    yield {"t": "done", "role": role, "model": model, "reply": msg, "tool_calls": collected}


# --------------------------------------------------------------------------- #
# Self-improvement: reflect_and_remember
# --------------------------------------------------------------------------- #
def _maybe_reflect(on_event: EventCb | None) -> None:
    n = memory.assistant_turn_count()
    if n and n % config.REFLECT_EVERY_N_TURNS == 0:
        # RAM guard: on a memory-starved machine, skip optional background work
        # rather than risk tipping into disk thrash / a hang.
        if config.ram_is_tight():
            return
        # Run in the background so it never blocks the reply, and on the already-hot
        # PRIMARY model so it doesn't load a second big model (the 8GB hang cause).
        import threading

        threading.Thread(target=reflect_and_remember, args=(None,), daemon=True).start()


def reflect_and_remember(on_event: EventCb | None = None) -> str:
    """
    Review recent history and save any durable lessons/corrections as notes.
    This is accumulated context, not weight-level learning (see README).
    """
    history = memory.recent_messages(limit=20)
    if not history:
        return "Nothing to reflect on yet."
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    prompt = (
        "Review this recent conversation. Extract at most 3 durable, reusable facts "
        "or corrections about the user or their setup that would help you next time. "
        "Return each as a single short line prefixed with '- '. If there is nothing "
        "worth saving, reply exactly 'NONE'.\n\n" + transcript
    )
    # Use the PRIMARY model (already resident) — never load a second big model here.
    _emit(on_event, "reflect", model=config.PRIMARY_MODEL)
    try:
        msg = ollama_check.chat(
            config.PRIMARY_MODEL,
            [{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 200},
        )
    except ollama_check.OllamaError as e:
        return f"(reflection skipped: {e})"
    text = (msg.get("content") or "").strip()
    if not text or text.upper().startswith("NONE"):
        return "Reflected — nothing new worth saving."
    saved = 0
    for line in text.splitlines():
        line = line.strip().lstrip("-").strip()
        if line and len(line) > 4:
            memory.add_note(line)
            saved += 1
    return f"Reflected and saved {saved} note(s)."
