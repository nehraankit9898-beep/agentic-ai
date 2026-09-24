"""Advanced: persistent long-term memory (SQLite via aiosqlite).

Two layers:
  1. Session transcripts — every user/assistant message is appended to the
     `messages` table so history survives server restarts and can be listed
     via /api/sessions. Each session gets a human-readable title derived
     from its first user message.
  2. Key-value facts — the agent can explicitly remember/recall durable
     facts ("user's name is X", "preferred language is Hindi") through the
     `memory_store` tool.

The DB path derives from settings.database_url (sqlite+aiosqlite:///...).
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from ..core.config import settings


def _db_path() -> Path:
    """Resolve the SQLite file path from DATABASE_URL."""
    url = settings.database_url
    m = re.search(r"aiosqlite:///(.+)$", url)
    raw = m.group(1) if m else url
    p = Path(raw)
    if not p.is_absolute():
        # Keep the db next to the workspace root rather than an arbitrary cwd.
        p = settings.workspace_path / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def derive_title(text: str, max_len: int = 60) -> str:
    """Human-friendly session title from the first user message."""
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return "New chat"
    clean = clean[:max_len]
    return clean + ("…" if len(clean) >= max_len and len(text.strip()) > max_len else "")


class MemoryStore:
    """Async SQLite-backed persistent memory for sessions + facts."""

    def __init__(self):
        self._db: Optional[aiosqlite.Connection] = None
        self.path = _db_path()

    async def init(self) -> None:
        if self._db is None:
            self._db = await aiosqlite.connect(self.path)
            await self._db.executescript(_SCHEMA)
            await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ---- transcript persistence -------------------------------------------

    async def append_message(
        self, session_id: str, role: str, content: str, metadata: dict | None = None
    ) -> None:
        await self.init()
        assert self._db is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO messages (session_id, role, content, metadata, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content[:8000],  # cap stored size per row
                json.dumps(metadata or {}, default=str),
                now,
            ),
        )
        # Upsert the session row; title comes from the first user message.
        if role == "user":
            await self._db.execute(
                "INSERT INTO sessions (session_id, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at",
                (session_id, derive_title(content), now, now),
            )
        else:
            await self._db.execute(
                "INSERT INTO sessions (session_id, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at",
                (session_id, "New chat", now, now),
            )
        await self._db.commit()

    async def load_session(self, session_id: str, limit: int = 50) -> list[dict]:
        await self.init()
        assert self._db is not None
        cur = await self._db.execute(
            "SELECT role, content, metadata, created_at FROM messages"
            " WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = await cur.fetchall()
        await cur.close()
        out = []
        for role, content, meta, ts in reversed(rows):
            try:
                metadata = json.loads(meta) if meta else {}
            except ValueError:
                metadata = {}
            out.append({"role": role, "content": content, "metadata": metadata, "created_at": ts})
        return out

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        await self.init()
        assert self._db is not None
        cur = await self._db.execute(
            "SELECT s.session_id, s.title, s.created_at, s.updated_at,"
            " COUNT(m.id) AS n"
            " FROM sessions s LEFT JOIN messages m ON m.session_id = s.session_id"
            " GROUP BY s.session_id"
            " ORDER BY s.updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [
            {
                "session_id": r[0],
                "title": r[1] or "New chat",
                "created_at": r[2],
                "last_active": r[3],
                "message_count": r[4],
            }
            for r in rows
        ]

    async def delete_session(self, session_id: str) -> int:
        await self.init()
        assert self._db is not None
        cur = await self._db.execute(
            "DELETE FROM messages WHERE session_id = ?", (session_id,)
        )
        await self._db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await self._db.commit()
        return cur.rowcount

    # ---- key/value facts ----------------------------------------------------

    async def set_fact(self, key: str, value: str) -> None:
        await self.init()
        assert self._db is not None
        await self._db.execute(
            "INSERT INTO facts (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
            " updated_at=excluded.updated_at",
            (key, value[:4000], datetime.now(timezone.utc).isoformat()),
        )
        await self._db.commit()

    async def get_fact(self, key: str) -> Optional[str]:
        await self.init()
        assert self._db is not None
        cur = await self._db.execute("SELECT value FROM facts WHERE key = ?", (key,))
        row = await cur.fetchone()
        await cur.close()
        return row[0] if row else None

    async def delete_fact(self, key: str) -> bool:
        await self.init()
        assert self._db is not None
        cur = await self._db.execute("DELETE FROM facts WHERE key = ?", (key,))
        await self._db.commit()
        return cur.rowcount > 0

    async def search_facts(self, query: str, limit: int = 10) -> list[dict]:
        await self.init()
        assert self._db is not None
        like = f"%{query}%"
        cur = await self._db.execute(
            "SELECT key, value, updated_at FROM facts"
            " WHERE key LIKE ? OR value LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (like, like, limit),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [{"key": r[0], "value": r[1], "updated_at": r[2]} for r in rows]

    async def all_facts(self, limit: int = 50) -> list[dict]:
        await self.init()
        assert self._db is not None
        cur = await self._db.execute(
            "SELECT key, value, updated_at FROM facts ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [{"key": r[0], "value": r[1], "updated_at": r[2]} for r in rows]


# Module-level singleton used by the API layer and the memory_store tool.
memory = MemoryStore()
