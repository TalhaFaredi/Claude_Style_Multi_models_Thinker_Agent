"""Session ledger: a numbered list of goals, decisions, numbers, rules and open questions, each linked to its
message. It changes by small edits (add, change, close), never by a full rewrite, which wears details away."""
from __future__ import annotations

import re

from app.core import db

KINDS = ("goal", "decision", "number", "rule", "question", "name", "date")


def ledger_items(chat_id: str, only_open: bool = False) -> list[dict]:
    sql = "SELECT * FROM ledger WHERE chat_id=?" + (" AND status!='closed'" if only_open else "") + " ORDER BY num"
    return [dict(r) for r in db.q(sql, (chat_id,))]


def ledger_apply(chat_id: str, ops: list[dict], src_seq: int | None = None) -> int:
    """Apply small edits. Returns how many were applied; malformed edits are skipped."""
    n = 0
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "add" and isinstance(op.get("text"), str) and op["text"].strip():
            num = (db.one("SELECT COALESCE(MAX(num),0)+1 AS n FROM ledger WHERE chat_id=?", (chat_id,)) or {"n": 1})["n"]
            k = op.get("type") if op.get("type") in KINDS else "decision"
            src = op.get("src") if isinstance(op.get("src"), int) else src_seq
            db.run("INSERT INTO ledger(chat_id,num,kind,text,src_seq,ts) VALUES(?,?,?,?,?,?)", (chat_id, num, k, op["text"].strip(), src, db.now()))
            n += 1
        elif kind == "change" and isinstance(op.get("num"), int) and isinstance(op.get("text"), str):
            db.run("UPDATE ledger SET text=?, status='changed', ts=? WHERE chat_id=? AND num=?", (op["text"].strip(), db.now(), chat_id, op["num"]))
            n += 1
        elif kind == "close" and isinstance(op.get("num"), int):
            db.run("UPDATE ledger SET status='closed', ts=? WHERE chat_id=? AND num=?", (db.now(), chat_id, op["num"]))
            n += 1
    return n


async def update_turn_ledger(chat_id: str, user_text: str, ctx) -> int:
    """Small per-turn edits, including temporary chats; durable memory remains separately optional."""
    from app import llm, prompts
    from app.core import config
    row = db.one("SELECT MAX(seq) AS n FROM messages WHERE chat_id=? AND role='user'", (chat_id,))
    seq = row["n"] if row else None
    listing = "\n".join(f"[{x['num']}] ({x['kind']}) {x['text']}" for x in ledger_items(chat_id))
    try:
        data, _ = await llm.ask_json(config.WRITER_MODEL, prompts.render("memory/ledger"),
                                     f"Current ledger:\n{listing}\n\nNew user message:\n{user_text}",
                                     stage="memory:ledger", ctx=ctx, max_tokens=700)
        ops = data.get("ops", []) if isinstance(data, dict) else []
        if isinstance(ops, list) and ops:
            return ledger_apply(chat_id, ops, seq)
    except Exception:
        pass
    # A failed writer never causes silent omission of an explicitly supplied rule/goal/fact.
    fact = re.compile(r"\b(my|our|remember|must|never|always|budget|deadline|goal|decided|prefer|name)\b", re.I)
    known = {x["text"] for x in ledger_items(chat_id)}
    ops = [{"op": "add", "type": "decision", "text": s.strip(), "src": seq}
           for s in re.split(r"(?<=[.!?])\s+|\n", user_text) if fact.search(s) and s.strip() not in known]
    return ledger_apply(chat_id, ops, seq)
