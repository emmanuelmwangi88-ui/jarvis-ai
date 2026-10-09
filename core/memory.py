"""
Conversation history + durable notes, in SQLite. Two tables:

  messages(id, ts, role, content, model)   -> rolling transcript
  notes(id, ts, key, content)              -> things remember() saved

Everything is local. No network.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any

from core import config


def _connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _connect() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS messages(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts REAL NOT NULL,
                   role TEXT NOT NULL,
                   content TEXT NOT NULL,
                   model TEXT
               )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS notes(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts REAL NOT NULL,
                   key TEXT,
                   content TEXT NOT NULL
               )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS skills(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts REAL NOT NULL,
                   name TEXT NOT NULL,
                   content TEXT NOT NULL,
                   uses INTEGER DEFAULT 0
               )"""
        )
        c.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS session_titles(session INTEGER PRIMARY KEY, title TEXT NOT NULL)")
        # Migration: give each message a session id so we can keep separate chats.
        cols = [r["name"] for r in c.execute("PRAGMA table_info(messages)").fetchall()]
        if "session" not in cols:
            c.execute("ALTER TABLE messages ADD COLUMN session INTEGER")
            c.execute("UPDATE messages SET session=1 WHERE session IS NULL")
        c.commit()


# --------------------------------------------------------------------------- #
# Sessions — each "chat" is a group of messages sharing one session id, so the
# user can browse past conversations and jump back into any of them.
# --------------------------------------------------------------------------- #
def _kv_get(key: str) -> str | None:
    with _connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
        row = c.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
    return row["v"] if row else None


def _kv_set(key: str, val: Any) -> None:
    with _connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
        c.execute(
            "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (key, str(val)),
        )
        c.commit()


def active_session() -> int:
    """The session new messages belong to. Adopts the latest existing one on first use."""
    v = _kv_get("active_session")
    if v is not None:
        return int(v)
    with _connect() as c:
        row = c.execute("SELECT MAX(session) AS m FROM messages").fetchone()
    sid = int(row["m"]) if row and row["m"] is not None else int(time.time())
    _kv_set("active_session", sid)
    return sid


def new_session() -> int:
    """Start a fresh chat with a unique id. Past chats stay saved and browsable."""
    with _connect() as c:
        row = c.execute("SELECT MAX(session) AS m FROM messages").fetchone()
    mx = int(row["m"]) if row and row["m"] is not None else 0
    try:
        cur = int(_kv_get("active_session") or 0)
    except (TypeError, ValueError):
        cur = 0
    sid = max(int(time.time()), mx + 1, cur + 1)
    _kv_set("active_session", sid)
    return sid


def load_session(sid: int) -> None:
    _kv_set("active_session", int(sid))


def list_sessions() -> list[dict[str, Any]]:
    """All past chats, newest first, each with a title taken from its first message."""
    active = active_session()
    with _connect() as c:
        rows = c.execute(
            """SELECT session, COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts
                   FROM messages WHERE session IS NOT NULL
                   GROUP BY session ORDER BY last_ts DESC"""
        ).fetchall()
        out = []
        for r in rows:
            sid = int(r["session"])
            t = c.execute(
                "SELECT content FROM messages WHERE session=? AND role='user' ORDER BY id LIMIT 1",
                (sid,),
            ).fetchone()
            custom = c.execute("SELECT title FROM session_titles WHERE session=?", (sid,)).fetchone()
            title = (custom["title"] if custom else (t["content"].strip()[:70] if t and t["content"] else "New chat"))
            out.append({
                "id": sid, "title": title, "count": int(r["n"]),
                "first_ts": r["first_ts"], "last_ts": r["last_ts"],
                "active": sid == active,
            })
    return out


def set_session_title(sid: int, title: str) -> None:
    title = " ".join((title or "").split())[:90] or "New chat"
    with _connect() as c:
        c.execute("INSERT INTO session_titles(session,title) VALUES(?,?) ON CONFLICT(session) DO UPDATE SET title=excluded.title", (int(sid), title))
        c.commit()


def session_title(sid: int) -> str:
    with _connect() as c:
        row = c.execute("SELECT title FROM session_titles WHERE session=?", (int(sid),)).fetchone()
        if row: return row["title"]
        row = c.execute("SELECT content FROM messages WHERE session=? AND role='user' ORDER BY id LIMIT 1", (int(sid),)).fetchone()
    return ((row["content"].strip()[:70] if row else "New chat"))


def session_transcript(sid: int, limit: int = 500) -> list[dict[str, Any]]:
    with _connect() as c:
        rows = c.execute(
            "SELECT ts, role, content, model FROM messages WHERE session=? ORDER BY id LIMIT ?",
            (int(sid), limit),
        ).fetchall()
    return [dict(r) for r in rows]


def add_message(role: str, content: str, model: str | None = None) -> None:
    with _connect() as c:
        c.execute(
            "INSERT INTO messages(ts, role, content, model, session) VALUES (?,?,?,?,?)",
            (time.time(), role, content, model, active_session()),
        )
        c.commit()


def recent_messages(limit: int = 20) -> list[dict[str, Any]]:
    """Most recent messages of the ACTIVE chat, oldest-first, as chat-ready dicts."""
    sid = active_session()
    with _connect() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE session=? ORDER BY id DESC LIMIT ?",
            (sid, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def transcript(limit: int = 200) -> list[dict[str, Any]]:
    """Active chat's messages with timestamp + model, oldest-first, for the history view."""
    sid = active_session()
    with _connect() as c:
        rows = c.execute(
            "SELECT ts, role, content, model FROM messages WHERE session=? ORDER BY id DESC LIMIT ?",
            (sid, limit),
        ).fetchall()
    return [
        {"ts": r["ts"], "role": r["role"], "content": r["content"], "model": r["model"]}
        for r in reversed(rows)
    ]


def assistant_turn_count() -> int:
    with _connect() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE role='assistant'"
        ).fetchone()
    return int(row["n"])


def clear_history() -> None:
    with _connect() as c:
        c.execute("DELETE FROM messages")
        c.commit()


# --------------------------------------------------------------------------- #
# Durable notes
# --------------------------------------------------------------------------- #
def add_note(content: str, key: str | None = None) -> int:
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO notes(ts, key, content) VALUES (?,?,?)",
            (time.time(), key, content),
        )
        c.commit()
        return int(cur.lastrowid)


def all_notes() -> list[dict[str, Any]]:
    with _connect() as c:
        rows = c.execute(
            "SELECT id, key, content, ts FROM notes ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def notes_as_context(limit: int = 40) -> str:
    """Render saved notes into a compact block for the system prompt."""
    notes = all_notes()[-limit:]
    if not notes:
        return ""
    lines = [f"- {n['content']}" for n in notes]
    return "Known facts and lessons from earlier sessions:\n" + "\n".join(lines)


# --------------------------------------------------------------------------- #
# Skills — self-taught reusable procedures
# --------------------------------------------------------------------------- #
def add_skill(name: str, content: str) -> int:
    with _connect() as c:
        # replace an existing skill of the same name
        c.execute("DELETE FROM skills WHERE name=?", (name,))
        cur = c.execute(
            "INSERT INTO skills(ts, name, content, uses) VALUES (?,?,?,0)",
            (time.time(), name, content),
        )
        c.commit()
        return int(cur.lastrowid)


def all_skills() -> list[dict[str, Any]]:
    with _connect() as c:
        rows = c.execute(
            "SELECT id, name, content, uses, ts FROM skills ORDER BY uses DESC, id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def skill_count() -> int:
    with _connect() as c:
        return int(c.execute("SELECT COUNT(*) AS n FROM skills").fetchone()["n"])


def skills_as_context(limit: int = 12) -> str:
    skills = all_skills()[:limit]
    if not skills:
        return ""
    lines = [f"- {s['name']}: {s['content']}" for s in skills]
    return "Self-taught skills you can reuse:\n" + "\n".join(lines)
