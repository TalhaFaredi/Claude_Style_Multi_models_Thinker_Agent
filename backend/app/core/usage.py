"""Logs and cost dashboard (spec Phase 4): every call is saved with model, tokens, cost and time."""
from __future__ import annotations

from datetime import datetime

from app.core import db


def month_start() -> float:
    n = datetime.now()
    return datetime(n.year, n.month, 1).timestamp()


def month_spent() -> float:
    r = db.one("SELECT COALESCE(SUM(cost),0) AS c FROM calls WHERE ts>=?", (month_start(),))
    return float(r["c"]) if r else 0.0


def report(since: float | None = None) -> dict:
    since = since or month_start()
    by_model = [dict(r) for r in db.q(
        "SELECT model, provider, COUNT(*) calls, COALESCE(SUM(in_tokens),0) in_tokens, COALESCE(SUM(out_tokens),0) out_tokens, "
        "COALESCE(SUM(cached_tokens),0) cached_tokens, ROUND(COALESCE(SUM(cost),0),6) cost, ROUND(AVG(ms)) avg_ms "
        "FROM calls WHERE ts>=? GROUP BY model, provider ORDER BY cost DESC", (since,))]
    by_stage = [dict(r) for r in db.q("SELECT stage, COUNT(*) calls, ROUND(COALESCE(SUM(cost),0),6) cost FROM calls WHERE ts>=? GROUP BY stage ORDER BY cost DESC", (since,))]
    errors = db.one("SELECT COUNT(*) n FROM calls WHERE ts>=? AND ok=0", (since,))["n"]
    total = db.one("SELECT COALESCE(SUM(cost),0) c, COUNT(*) n, COALESCE(SUM(usage_estimated),0) estimated FROM calls WHERE ts>=?", (since,))
    return {"since": since, "totalUsd": round(float(total["c"]), 6), "calls": total["n"], "failedCalls": errors,
            "estimatedCalls": total["estimated"], "byModel": by_model, "byStage": by_stage}


def chat_cost(chat_id: str) -> float:
    r = db.one("SELECT COALESCE(SUM(cost),0) AS c FROM calls WHERE chat_id=?", (chat_id,))
    return float(r["c"]) if r else 0.0
