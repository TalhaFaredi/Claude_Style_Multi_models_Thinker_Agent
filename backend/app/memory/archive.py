"""The Archive: chats and every message word for word, with its time, searchable (never deleted by
compaction; only the user deletes a chat)."""
from __future__ import annotations

import json
import re
import uuid

from app.core import db
from app.core.tokens import estimate_tokens
from app.memory.settings import get_settings


def create_chat(title: str = "New chat", temp: bool = False, chat_id: str | None = None) -> dict:
    cid = chat_id or uuid.uuid4().hex[:12]
    t = db.now()
    db.run("INSERT OR IGNORE INTO chats(id,title,created,updated,temp) VALUES(?,?,?,?,?)", (cid, title[:80], t, t, 1 if temp else 0))
    return get_chat(cid)  # type: ignore[return-value]


def get_chat(chat_id: str) -> dict | None:
    r = db.one("SELECT * FROM chats WHERE id=?", (chat_id,))
    return dict(r) if r else None


def ensure_chat(chat_id: str) -> dict:
    return get_chat(chat_id) or create_chat(chat_id=chat_id, temp=bool(get_settings()["tempChat"]))


def list_chats(q: str = "") -> list[dict]:
    has_msgs = "EXISTS (SELECT 1 FROM messages m WHERE m.chat_id=c.id)"   # a chat with no message yet is not listed
    if q.strip():
        rows = db.q(f"SELECT DISTINCT c.* FROM chats c LEFT JOIN msg_fts f ON f.chat_id=c.id AND f.msg_fts MATCH ? "
                    f"WHERE {has_msgs} AND (c.title LIKE ? OR f.msg_id IS NOT NULL) ORDER BY c.updated DESC LIMIT 100", (db.fts_query(q) or '""', f"%{q}%"))
    else:
        rows = db.q(f"SELECT c.* FROM chats c WHERE {has_msgs} ORDER BY c.updated DESC LIMIT 100")
    return [{"id": r["id"], "title": r["title"], "updated": r["updated"], "temp": bool(r["temp"])} for r in rows]


def rename_chat(chat_id: str, title: str) -> None:
    db.run("UPDATE chats SET title=? WHERE id=?", (title[:80], chat_id))


def add_message(chat_id: str, role: str, content: str, *, model: str | None = None, cost: float = 0.0, meta: dict | None = None,
                imported: bool = False, mid: str | None = None, ts: float | None = None) -> dict:
    ensure_chat(chat_id)
    mid = mid or uuid.uuid4().hex[:16]
    seq = (db.one("SELECT COALESCE(MAX(seq),0)+1 AS n FROM messages WHERE chat_id=?", (chat_id,)) or {"n": 1})["n"]
    tokens = estimate_tokens(content)
    t = ts or db.now()
    with db.tx() as c:
        c.execute("INSERT INTO messages(id,chat_id,seq,role,content,ts,model,tokens,cost,meta,imported) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (mid, chat_id, seq, role, content, t, model, tokens, cost, json.dumps(meta) if meta else None, 1 if imported else 0))
        if role in ("user", "assistant"):
            c.execute("INSERT INTO msg_fts(content,chat_id,msg_id) VALUES(?,?,?)", (content, chat_id, mid))
        c.execute("UPDATE chats SET updated=? WHERE id=?", (t, chat_id))
        if role == "user" and seq <= 2:
            c.execute("UPDATE chats SET title=? WHERE id=? AND title='New chat'", (re.sub(r"\s+", " ", content).strip()[:48] or "New chat", chat_id))
    return {"id": mid, "seq": seq, "tokens": tokens}


def update_message(mid: str, content: str | None = None, meta: dict | None = None, cost: float | None = None, model: str | None = None) -> None:
    if content is not None:
        db.run("UPDATE messages SET content=?, tokens=? WHERE id=?", (content, estimate_tokens(content), mid))
        db.run("DELETE FROM msg_fts WHERE msg_id=?", (mid,))
        row = db.one("SELECT chat_id, role FROM messages WHERE id=?", (mid,))
        if row and content and row["role"] in ("user", "assistant"):
            db.run("INSERT INTO msg_fts(content,chat_id,msg_id) VALUES(?,?,?)", (content, row["chat_id"], mid))
    if meta is not None:
        db.run("UPDATE messages SET meta=? WHERE id=?", (json.dumps(meta), mid))
    if cost is not None:
        db.run("UPDATE messages SET cost=? WHERE id=?", (cost, mid))
    if model is not None:
        db.run("UPDATE messages SET model=? WHERE id=?", (model, mid))


def delete_message(chat_id: str, mid: str) -> bool:
    """Used by Retry. Scoped to the chat, so one chat can never delete another chat's message."""
    row = db.one("SELECT id FROM messages WHERE id=? AND chat_id=?", (mid, chat_id))
    if not row:
        return False
    with db.tx() as c:
        c.execute("DELETE FROM msg_fts WHERE msg_id=? AND chat_id=?", (mid, chat_id))
        c.execute("DELETE FROM messages WHERE id=? AND chat_id=?", (mid, chat_id))
    return True


def rate_message(mid: str, value: int) -> bool:
    return db.run("UPDATE messages SET rating=? WHERE id=? AND role='assistant'", (value, mid)) is not None


def ui_messages(chat_id: str) -> list[dict]:
    """The chat as the frontend renders it. Assistant meta holds the full answer view saved at the end of the run."""
    out = []
    for r in db.q("SELECT * FROM messages WHERE chat_id=? ORDER BY seq", (chat_id,)):
        meta = json.loads(r["meta"]) if r["meta"] else {}
        if not isinstance(meta, dict):
            meta = {}
        if r["role"] == "user":
            out.append({"id": r["id"], "role": "user", "text": r["content"], "files": meta.get("files", [])})
        elif r["role"] == "sys":
            out.append({"id": r["id"], "role": "sys", "text": r["content"]})
        else:
            view = meta.get("view") if isinstance(meta.get("view"), dict) else {}
            out.append({**view, "id": r["id"], "role": "ai", "text": r["content"], "summarized": r["summarized_into"] is not None})
    return out


def delete_chat(chat_id: str, delete_memories: bool) -> dict:
    """C42: remove the chat from every store, index and cache. The user decides about the memories it created."""
    from app.files import forget_chat
    from app.memory.facts import delete_fact
    from app.output import delete_chat_artifacts

    fact_ids = [r["id"] for r in db.q("SELECT id FROM facts WHERE chat_id=?", (chat_id,))] if delete_memories else []
    with db.tx() as c:
        c.execute("DELETE FROM msg_fts WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM ledger WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM summaries WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM chat_facts WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        # the cost log (calls table) is kept on purpose: it is the books and holds no chat content
    for fid in fact_ids:
        delete_fact(fid)
    files_purged = forget_chat(chat_id)
    artifacts = delete_chat_artifacts(chat_id)
    return {"deleted": True, "factsDeleted": len(fact_ids), "memoriesKept": not delete_memories,
            "filesRemoved": files_purged, "outputsRemoved": artifacts}
