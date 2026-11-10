"""C40: "as I said last week" -> search the Archive of THIS chat with a date filter and bring back the original messages."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.core import db

_RECALL = re.compile(r"\b(as i said|i said|i told you|you said|we discussed|earlier|last (week|month|time)|yesterday|remember when|before|previously|ago)\b", re.I)


def date_range(text: str) -> tuple[float, float] | None:
    t, n = text.lower(), datetime.now()
    if "yesterday" in t:
        d = (n - timedelta(days=1)).replace(hour=0, minute=0, second=0)
        return d.timestamp(), (d + timedelta(days=1)).timestamp()
    if "last week" in t:
        return (n - timedelta(days=14)).timestamp(), (n - timedelta(days=5)).timestamp()
    if "last month" in t:
        return (n - timedelta(days=62)).timestamp(), (n - timedelta(days=25)).timestamp()
    m = re.search(r"(\d+)\s+(day|week|month)s?\s+ago", t)
    if m:
        days = int(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2)]
        c = n - timedelta(days=days)
        return (c - timedelta(days=max(1, days // 4))).timestamp(), (c + timedelta(days=max(1, days // 4))).timestamp()
    return None


def recall_originals(chat_id: str, text: str, k: int = 6, summarized_only: bool = False) -> list[dict]:
    if not _RECALL.search(text) and not summarized_only:
        return []
    fq = db.fts_query(text)
    if not fq:
        return []
    rng = date_range(text)
    sql = ("SELECT m.* FROM msg_fts f JOIN messages m ON m.id=f.msg_id WHERE msg_fts MATCH ? AND m.chat_id=?"
           + (" AND m.summarized_into IS NOT NULL" if summarized_only and not _RECALL.search(text) else "")
           + (" AND m.ts BETWEEN ? AND ?" if rng else "") + " ORDER BY bm25(msg_fts) LIMIT ?")
    return [dict(r) for r in db.q(sql, (fq, chat_id, *(rng or ()), k))]
