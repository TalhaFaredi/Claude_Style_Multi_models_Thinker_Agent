"""Long-term memory: facts about the user and their projects, each with a date and a source.
A changed fact replaces the old one, which is marked "replaced" with the date, not deleted (C39).
Deleting a fact really deletes it (C42). The Memory Writer runs after the reply, off the critical path."""
from __future__ import annotations

import re
from datetime import datetime

from app import llm, prompts
from app.core import config, db
from app.memory.archive import get_chat
from app.memory.settings import long_memory_on


def add_fact(text: str, source: str, chat_id: str | None, replaces: int | None = None,
             ts: float | None = None, replaced_at: float | None = None) -> int:
    fid = db.run("INSERT INTO facts(text,source,chat_id,ts) VALUES(?,?,?,?)", (text.strip(), source, chat_id, ts if ts is not None else db.now()))
    db.run("INSERT INTO fact_fts(text,fact_id) VALUES(?,?)", (text, fid))
    if replaces:   # C39: keep the new one, mark the old one "replaced" with the date (history is kept)
        db.run("UPDATE facts SET replaced_by=?, replaced_at=? WHERE id=? AND deleted=0", (fid, replaced_at if replaced_at is not None else db.now(), replaces))
    return fid


def delete_fact(fid: int) -> bool:
    """Remove the fact from the table and the search index (no soft delete: the text is gone)."""
    if not db.one("SELECT id FROM facts WHERE id=?", (fid,)):
        return False
    with db.tx() as c:
        c.execute("DELETE FROM fact_fts WHERE fact_id=?", (fid,))
        c.execute("DELETE FROM facts WHERE id=?", (fid,))
        c.execute("DELETE FROM chat_facts WHERE fact_id=?", (fid,))
    return True


def list_facts(include_history: bool = False) -> list[dict]:
    sql = "SELECT * FROM facts WHERE deleted=0" + ("" if include_history else " AND replaced_by IS NULL") + " ORDER BY ts DESC LIMIT 200"
    out = []
    for r in db.q(sql):
        src = r["source"] or ""
        out.append({"id": r["id"], "text": r["text"], "source": f"{datetime.fromtimestamp(r['ts']).strftime('%b %d')}, {src}".strip(", "),
                    "replaced": r["replaced_by"] is not None,
                    "replacedOn": datetime.fromtimestamp(r["replaced_at"]).strftime("%b %d") if r["replaced_at"] else None})
    return out


def relevant_facts(query: str, k: int = 6, include_history: bool = False) -> list[dict]:
    """Current facts that match the question, plus a few recent ones so preferences are not forgotten."""
    fq = db.fts_query(query)
    rows = []
    if fq:
        rows = db.q("SELECT f.* FROM fact_fts x JOIN facts f ON f.id=x.fact_id WHERE fact_fts MATCH ? AND f.deleted=0 "
                    + ("" if include_history else "AND f.replaced_by IS NULL ") +
                    "ORDER BY bm25(fact_fts) LIMIT ?", (fq, k))
    if len(rows) < 3:
        seen = {r["id"] for r in rows}
        rows += [r for r in db.q("SELECT * FROM facts WHERE deleted=0 AND replaced_by IS NULL ORDER BY ts DESC LIMIT 3") if r["id"] not in seen]
    return [dict(r) for r in rows[:k]]


_FACT_GATE = re.compile(r"\b(i|my|we|our|me|mine|prefer|remember|always|never|budget|deadline|name is|working on|project|decid|plan to|call me)\b", re.I)


async def write_turn_memory(chat_id: str, user_text: str, assistant_text: str, ctx: llm.CallContext) -> dict:
    """Memory Writer. C41: nothing goes to long-term memory in a temporary chat or when memory is off."""
    chat = get_chat(chat_id)
    from app.memory.ledger import update_turn_ledger
    await update_turn_ledger(chat_id, user_text, ctx)
    if not long_memory_on(chat):
        return {"skipped": True}
    if not user_text.strip() or not (_FACT_GATE.search(user_text) or len(user_text) > 240):
        return {"skipped": True}   # cheap gate: most turns hold nothing worth remembering
    existing = relevant_facts(user_text, 6)
    listing = "\n".join(f"[{f['id']}] {f['text']}" for f in existing) or "(none)"
    try:
        data, _ = await llm.ask_json(config.WRITER_MODEL, prompts.render("memory/facts"),
                                     f"Existing facts:\n{listing}\n\nUser message:\n{user_text[:1500]}", stage="memory:facts", ctx=ctx, max_tokens=300)
    except Exception:
        return {"skipped": True}
    n = 0
    for f in (data or {}).get("facts", [])[:5] if isinstance(data, dict) else []:
        if isinstance(f, dict) and isinstance(f.get("text"), str) and f["text"].strip():
            rep = f.get("replaces") if isinstance(f.get("replaces"), int) and any(e["id"] == f["replaces"] for e in existing) else None
            add_fact(f["text"], f'"{chat["title"]}"', chat_id, rep)
            n += 1
    return {"facts": n}
