"""SQLite storage. The spec suggests PostgreSQL + pgvector for production; SQLite + FTS5 gives the same
data model with zero setup. One connection guarded by a lock. Every row of user data carries a user_id and every query filters
by the signed-in user (db.uid(), set per request in core/middleware.py); user 0 is the single local user when accounts are off.

Tables
  chats, messages, msg_fts          the Archive (every message word for word, keyword-searchable)
  ledger, summaries, facts, fact_fts  session ledger, checked summaries, long-term facts
  files, file_chats, readings,      attachment pipeline: fingerprints, Parse Cache, chunks + search index
  chunks, chunk_fts
  artifacts                         files the Output Builder made (PDF, web page, code ...)
  calls                             one row per model call: tokens, cost, time (the books; no content)
  settings                          user settings as JSON values
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterable

from app.core.config import DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE COLLATE NOCASE, pw_hash TEXT NOT NULL,
  created REAL NOT NULL, last_login REAL, is_admin INTEGER NOT NULL DEFAULT 0, disabled INTEGER NOT NULL DEFAULT 0,
  monthly_cap REAL
);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created REAL NOT NULL, last_seen REAL NOT NULL, expires REAL NOT NULL,
  ip TEXT, agent TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS password_resets(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chats(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
  window_cap INTEGER, calib REAL NOT NULL DEFAULT 1.0, last_model TEXT, temp INTEGER NOT NULL DEFAULT 0,
  user_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages(
  id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL,
  content TEXT NOT NULL, ts REAL NOT NULL, model TEXT, tokens INTEGER NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0, meta TEXT, pinned INTEGER NOT NULL DEFAULT 0,
  summarized_into INTEGER, imported INTEGER NOT NULL DEFAULT 0, rating INTEGER
);
CREATE INDEX IF NOT EXISTS ix_msg_chat ON messages(chat_id, seq);
CREATE VIRTUAL TABLE IF NOT EXISTS msg_fts USING fts5(content, chat_id UNINDEXED, msg_id UNINDEXED);
CREATE TABLE IF NOT EXISTS ledger(
  id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL, num INTEGER NOT NULL, kind TEXT NOT NULL,
  text TEXT NOT NULL, src_seq INTEGER, status TEXT NOT NULL DEFAULT 'open', ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ledger_chat ON ledger(chat_id, num);
CREATE TABLE IF NOT EXISTS summaries(
  id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL, from_seq INTEGER NOT NULL, to_seq INTEGER NOT NULL,
  text TEXT NOT NULL, seqs TEXT NOT NULL, tokens INTEGER NOT NULL, ts REAL NOT NULL, merged_into INTEGER
);
CREATE TABLE IF NOT EXISTS facts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, source TEXT, chat_id TEXT, ts REAL NOT NULL,
  replaced_by INTEGER, replaced_at REAL, deleted INTEGER NOT NULL DEFAULT 0, user_id INTEGER NOT NULL DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS fact_fts USING fts5(text, fact_id UNINDEXED);
CREATE TABLE IF NOT EXISTS calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, run_id TEXT, chat_id TEXT, stage TEXT, provider TEXT,
  model TEXT, in_tokens INTEGER, out_tokens INTEGER, cached_tokens INTEGER, reasoning_tokens INTEGER,
  cost REAL, ms INTEGER, ok INTEGER, error TEXT, user_id INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_calls_ts ON calls(ts);
CREATE TABLE IF NOT EXISTS files(
  fingerprint TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL, mime TEXT, pages INTEGER NOT NULL,
  kinds TEXT NOT NULL, path TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS file_chats(chat_id TEXT NOT NULL, fingerprint TEXT NOT NULL, ts REAL NOT NULL, reader TEXT, PRIMARY KEY(chat_id, fingerprint));
CREATE TABLE IF NOT EXISTS readings(
  fingerprint TEXT NOT NULL, reader TEXT NOT NULL, version INTEGER NOT NULL, pages TEXT NOT NULL, card TEXT,
  cost REAL NOT NULL DEFAULT 0, ts REAL NOT NULL, PRIMARY KEY(fingerprint, reader, version)
);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL, reader TEXT NOT NULL, idx INTEGER NOT NULL,
  page INTEGER, section TEXT, kind TEXT, text TEXT NOT NULL, tokens INTEGER NOT NULL, embedding BLOB
);
CREATE INDEX IF NOT EXISTS ix_chunks_fp ON chunks(fingerprint, reader, idx);
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text, chunk_id UNINDEXED);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts(
  id TEXT PRIMARY KEY, chat_id TEXT, name TEXT NOT NULL, path TEXT NOT NULL, mime TEXT, pages INTEGER, sources INTEGER, ts REAL NOT NULL,
  user_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS chat_facts(chat_id TEXT NOT NULL, fact_id INTEGER NOT NULL, PRIMARY KEY(chat_id,fact_id));
CREATE TABLE IF NOT EXISTS tool_calls(
 id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL NOT NULL,run_id TEXT,chat_id TEXT,scope_id TEXT,
 tool TEXT NOT NULL,ms INTEGER NOT NULL,ok INTEGER NOT NULL,error TEXT
);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

# The signed-in user of the current request (and of every task and thread it starts: contextvars are copied).
# 0 is the single local user: no accounts, and everything stored before accounts existed.
_uid: ContextVar[int] = ContextVar("current_user_id", default=0)


def uid() -> int:
    return _uid.get()


def set_uid(user_id: int):
    """Returns a token for reset_uid()."""
    return _uid.set(int(user_id))


def reset_uid(token) -> None:
    _uid.reset(token)


@contextmanager
def as_user(user_id: int):
    token = _uid.set(int(user_id))
    try:
        yield
    finally:
        _uid.reset(token)


def now() -> float:
    return time.time()


def _open(path) -> sqlite3.Connection:
    c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    # Additive migrations preserve existing local archives and cached readings.
    for table, name, definition in (
        ("file_chats", "reader", "TEXT"),
        ("chunks", "embedding_model", "TEXT"),
        ("calls", "usage_estimated", "INTEGER NOT NULL DEFAULT 0"),
        ("calls", "completed", "INTEGER NOT NULL DEFAULT 1"),
        ("messages", "origin_id", "TEXT"),
        ("chats", "user_id", "INTEGER NOT NULL DEFAULT 0"),
        ("facts", "user_id", "INTEGER NOT NULL DEFAULT 0"),
        ("calls", "user_id", "INTEGER NOT NULL DEFAULT 0"),
        ("artifacts", "user_id", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    c.executescript("""
CREATE INDEX IF NOT EXISTS ix_chats_user ON chats(user_id, updated);
CREATE INDEX IF NOT EXISTS ix_facts_user ON facts(user_id);
CREATE INDEX IF NOT EXISTS ix_calls_user ON calls(user_id, ts);
CREATE INDEX IF NOT EXISTS ix_artifacts_user ON artifacts(user_id);
""")
    return c


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = _open(DATA_DIR / "assistant.db")
        _conn.execute("PRAGMA busy_timeout=10000")   # the backup job and the admin tool open their own connections
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA secure_delete=ON")   # deleted rows are overwritten on disk, not just unlinked
    return _conn


def reset_for_tests(path: str = ":memory:") -> None:
    """Point the module at a fresh database (tests only)."""
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = _open(path)


def q(sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, tuple(args)).fetchall()


def one(sql: str, args: Iterable[Any] = ()) -> sqlite3.Row | None:
    with _lock:
        return conn().execute(sql, tuple(args)).fetchone()


def run(sql: str, args: Iterable[Any] = ()) -> int:
    """Execute a write; returns lastrowid."""
    with _lock:
        return conn().execute(sql, tuple(args)).lastrowid or 0


@contextmanager
def tx():
    """Atomic group of writes."""
    with _lock:
        c = conn()
        c.execute("BEGIN")
        try:
            yield c
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise


_STOP = set("the a an and or of to in on for with is are was were be this that it as at by from what which who how why do does did can could should would i you we they my your our".split())


def fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 OR query (quoted words, no operators)."""
    words = [w for w in re.findall(r"[\w]{2,}", text.lower()) if w not in _STOP][:24]
    return " OR ".join(f'"{w}"' for w in words)


def setting_key(key: str, user_id: int | None = None) -> str:
    """Settings are per user. The local user (0) keeps the plain key, so a database from before accounts still works."""
    u = uid() if user_id is None else user_id
    return key if u == 0 else f"u{u}:{key}"


def get_setting(key: str, default: Any = None) -> Any:
    r = one("SELECT value FROM settings WHERE key=?", (setting_key(key),))
    return json.loads(r["value"]) if r else default


def set_setting(key: str, value: Any) -> None:
    run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (setting_key(key), json.dumps(value)))
