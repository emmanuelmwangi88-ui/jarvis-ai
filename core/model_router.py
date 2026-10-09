"""
Route a single user message to a model role. Deliberately simple and transparent —
keyword + length heuristics, no ML. Returns (role, model_name, wants_tools).

Speed note: when config.SINGLE_MODEL_MODE is on (the default on 8GB RAM), chat /
reason / general-tool turns all resolve to config.PRIMARY_MODEL so Ollama keeps ONE
model hot instead of reloading a different model on every message. Explicit code
tasks still use the coder model, and screen questions still use the vision model —
those swaps are worth it.
"""
from __future__ import annotations

import re

from core import config

# keyword sets per role
_CODE_WORDS = {
    "code", "script", "function", "bug", "compile", "git", "refactor",
    "python", "javascript", "typescript", "regex", "stack trace", "traceback",
    "syntax", "debug", "class", "api", "sql", "docker", "html", "css", "rust",
    "java", "c++", "golang", "algorithm", "unit test", "exception", "npm", "pip",
}
_TOOL_WORDS = {
    "file", "files", "folder", "directory", "save", "write", "read", "open",
    "run", "terminal", "command", "shell", "execute", "install",
    "email", "mail", "send",
    "window", "windows", "app", "application", "clipboard", "copy", "paste",
    "download", "delete", "move", "rename", "screenshot", "schedule", "remind",
    "launch", "kill", "close", "volume", "brightness", "zip", "unzip",
}
_WEB_WORDS = {
    "search", "google", "look up", "lookup", "web", "internet", "online",
    "latest", "news", "today", "current", "recent", "price", "weather",
    "who is", "what is", "when is", "where is", "how much", "score",
    "release", "version", "update", "stock", "定义",
    "research", "sources", "cite", "citation", "paper", "study", "review of",
    "compare prices", "find out", "according to",
}
_REASON_WORDS = {
    "why", "how come", "compare", "difference", "design", "architecture",
    "explain", "analyze", "analyse", "trade-off", "tradeoff", "pros and cons",
    "strategy", "plan", "reason", "prove", "derive", "essay", "summarize",
    "brainstorm", "outline", "critique", "evaluate", "step by step",
}
_VISION_WORDS = {
    "screenshot", "screen", "what do you see", "on my screen", "look at",
    "this image", "the picture", "what's shown",
}

# Friendly metadata per role — surfaced on the orb so the user SEES how their
# prompt was classified and which model was assigned to it.
CATEGORIES: dict[str, dict[str, str]] = {
    "vision":   {"label": "Vision",    "hint": "reading the screen"},
    "code":     {"label": "Code",      "hint": "writing / debugging code"},
    "research": {"label": "Research",  "hint": "searching the web"},
    "tools":    {"label": "Actions",   "hint": "acting on your machine"},
    "reason":   {"label": "Reasoning", "hint": "deep analysis"},
    "chat":     {"label": "Chat",      "hint": "general conversation"},
    "fast":     {"label": "Quick",     "hint": "instant reply"},
}


def label(role: str) -> str:
    return CATEGORIES.get(role, {}).get("label", role.title())


_LONG_MESSAGE_CHARS = 220
_TRIVIAL_CHARS = 24
_GREETINGS = {
    "hi", "hey", "hello", "yo", "sup", "thanks", "thank you", "ok", "okay",
    "cool", "nice", "great", "lol", "gm", "good morning", "good night", "bye",
}


def _has_word(text: str, words: set[str]) -> bool:
    lowered = text.lower()
    for w in words:
        if " " in w:
            if w in lowered:
                return True
        elif re.search(rf"\b{re.escape(w)}\b", lowered):
            return True
    return False


def route(message: str) -> tuple[str, str, bool]:
    """
    Decide which role handles this message.

    Returns:
        role         'vision' | 'code' | 'tools' | 'reason' | 'chat' | 'fast'
        model_name   the concrete Ollama model for that role
        wants_tools  whether the agent loop should offer tools to the model
    """
    text = (message or "").strip()
    lowered = text.lower()
    single = config.SINGLE_MODEL_MODE
    primary = config.PRIMARY_MODEL

    # Vision short-circuits — handled by a direct vision call in the agent.
    if _has_word(text, _VISION_WORDS):
        return "vision", config.MODELS["vision"], False

    # Trivial greetings / acknowledgements -> the tiniest model, no tools.
    if len(text) <= _TRIVIAL_CHARS and (
        lowered.strip("!?. ") in _GREETINGS or lowered in _GREETINGS
    ):
        return "fast", config.MODELS["fast"], False

    # Anything web-ish or system-ish needs tools available.
    web = _has_word(text, _WEB_WORDS)
    tool = _has_word(text, _TOOL_WORDS)
    code = _has_word(text, _CODE_WORDS)

    # Explicit coding work goes to the coder model even in single-model mode —
    # the quality gain is worth one swap.
    if code:
        return "code", config.MODELS["tools"], True

    # Web/research questions — needs tools to search & fetch, then synthesize.
    if web and not tool:
        model = primary if single else config.MODELS["reason"]
        return "research", model, True

    if web or tool:
        model = primary if single else config.MODELS["tools"]
        return "tools", model, True

    # Long or explicitly analytical -> the reasoning model (or primary if single).
    if len(text) > _LONG_MESSAGE_CHARS or _has_word(text, _REASON_WORDS):
        model = primary if single else config.MODELS["reason"]
        return "reason", model, True

    # Default: primary general model. Tools stay available but rarely fire.
    return "chat", primary, True
