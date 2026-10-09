"""
Tiny local RAG store. Documents are chunked, embedded with nomic-embed-text via
Ollama, and stored in SQLite. Retrieval is brute-force cosine similarity — plenty
fast for a personal knowledge base of a few thousand chunks, and zero extra deps.
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from core import config, ollama_check


def _connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.RAG_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _connect() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS chunks(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts REAL NOT NULL,
                   source TEXT NOT NULL,
                   chunk_index INTEGER NOT NULL,
                   text TEXT NOT NULL,
                   embedding TEXT NOT NULL
               )"""
        )
        c.commit()


def _chunk(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    text = text.strip()
    if not text:
        return []
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def remember_document(path: str) -> str:
    """
    Read a text file, chunk + embed it, and store it. Returns a status string.
    Non-text/binary files are rejected with a friendly message.
    """
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        return f"No such file: {path}"
    try:
        raw = p.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError):
        return f"Can't index {p.name}: not a UTF-8 text file."

    chunks = _chunk(raw)
    if not chunks:
        return f"{p.name} is empty."

    init()
    stored = 0
    with _connect() as c:
        # replace any prior copy of this source
        c.execute("DELETE FROM chunks WHERE source=?", (str(p),))
        for i, ch in enumerate(chunks):
            vec = ollama_check.embed(config.MODELS["embed"], ch)
            c.execute(
                "INSERT INTO chunks(ts, source, chunk_index, text, embedding) "
                "VALUES (?,?,?,?,?)",
                (time.time(), str(p), i, ch, json.dumps(vec)),
            )
            stored += 1
        c.commit()
    return f"Indexed {p.name}: {stored} chunk(s) now searchable."


def search_knowledge(query: str, top_k: int = 4) -> str:
    """Return the most relevant stored chunks for a query, formatted for the model."""
    init()
    with _connect() as c:
        rows = c.execute(
            "SELECT source, chunk_index, text, embedding FROM chunks"
        ).fetchall()
    if not rows:
        return "Knowledge base is empty. Use remember_document(path) to add files."

    qvec = ollama_check.embed(config.MODELS["embed"], query)
    scored: list[tuple[float, sqlite3.Row]] = []
    for r in rows:
        vec = json.loads(r["embedding"])
        scored.append((_cosine(qvec, vec), r))
    scored.sort(key=lambda t: t[0], reverse=True)

    hits = scored[:top_k]
    if not hits or hits[0][0] <= 0:
        return "No relevant passages found in the knowledge base."

    parts: list[str] = []
    for score, r in hits:
        name = Path(r["source"]).name
        parts.append(
            f"[{name} #{r['chunk_index']}  (relevance {score:.2f})]\n{r['text']}"
        )
    return "\n\n---\n\n".join(parts)


def stats() -> dict[str, Any]:
    init()
    with _connect() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        srcs = c.execute("SELECT COUNT(DISTINCT source) AS n FROM chunks").fetchone()["n"]
    return {"chunks": int(n), "documents": int(srcs)}
