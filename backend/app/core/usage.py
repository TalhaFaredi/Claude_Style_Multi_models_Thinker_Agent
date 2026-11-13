"""Logs and cost dashboard (spec Phase 4): every call is saved with model, tokens, cost and time."""
from __future__ import annotations

from datetime import datetime

from app.core import config, db


class SpendBlocked(Exception):
    """A monthly allowance is used up. The API answers 402 with this message."""


def month_start() -> float:
    n = datetime.now()
    return datetime(n.year, n.month, 1).timestamp()


def month_spent() -> float:
    r = db.one("SELECT COALESCE(SUM(cost),0) AS c FROM calls WHERE ts>=? AND user_id=?", (month_start(), db.uid()))
    return float(r["c"]) if r else 0.0


def reading_spent() -> float:
    """This month's file-reading and indexing spend of the current user."""
    r = db.one("SELECT COALESCE(SUM(cost),0) AS c FROM calls WHERE ts>=? AND user_id=? AND ok=1 AND (stage LIKE 'file:%' OR stage LIKE 'embed:%')",
               (month_start(), db.uid()))
    return float(r["c"]) if r else 0.0


def global_month_spent() -> float:
    r = db.one("SELECT COALESCE(SUM(cost),0) AS c FROM calls WHERE ts>=?", (month_start(),))
    return float(r["c"]) if r else 0.0


def month_cap() -> float:
    """The most the current user may spend per month: their own cap if an admin set one, else the default."""
    if not config.AUTH_REQUIRED:
        return 1000.0
    u = db.one("SELECT monthly_cap FROM users WHERE id=?", (db.uid(),))
    return float(u["monthly_cap"]) if u and u["monthly_cap"] is not None else config.DEFAULT_USER_MONTHLY_USD


def ensure_can_spend() -> None:
    """Call before anything that costs money. Local single-user mode has no caps."""
    if not config.AUTH_REQUIRED:
        return
    if config.GLOBAL_MONTHLY_USD > 0 and global_month_spent() >= config.GLOBAL_MONTHLY_USD:
        raise SpendBlocked("The service has reached its usage limit for this month. Please try again next month.")
    cap, spent = month_cap(), month_spent()
    if spent >= cap - 1e-9:
        raise SpendBlocked(f"You have used your monthly allowance (${cap:.2f}). It renews on the 1st of next month.")


def limit_budget(requested: float) -> float:
    """One question may not exceed the per-question ceiling or what is left of the user's month."""
    if not config.AUTH_REQUIRED:
        return requested
    return max(0.0, min(requested, config.MAX_RUN_USD, month_cap() - month_spent()))


def report(since: float | None = None) -> dict:
    since = since or month_start()
    by_model = [dict(r) for r in db.q(
        "SELECT model, provider, COUNT(*) calls, COALESCE(SUM(in_tokens),0) in_tokens, COALESCE(SUM(out_tokens),0) out_tokens, "
        "COALESCE(SUM(cached_tokens),0) cached_tokens, ROUND(COALESCE(SUM(cost),0),6) cost, ROUND(AVG(ms)) avg_ms "
        "FROM calls WHERE ts>=? AND user_id=? GROUP BY model, provider ORDER BY cost DESC", (since, db.uid()))]
    by_stage = [dict(r) for r in db.q("SELECT stage, COUNT(*) calls, ROUND(COALESCE(SUM(cost),0),6) cost FROM calls WHERE ts>=? AND user_id=? GROUP BY stage ORDER BY cost DESC", (since, db.uid()))]
    errors = db.one("SELECT COUNT(*) n FROM calls WHERE ts>=? AND user_id=? AND ok=0", (since, db.uid()))["n"]
    total = db.one("SELECT COALESCE(SUM(cost),0) c, COUNT(*) n, COALESCE(SUM(usage_estimated),0) estimated FROM calls WHERE ts>=? AND user_id=?", (since, db.uid()))
    return {"since": since, "totalUsd": round(float(total["c"]), 6), "calls": total["n"], "failedCalls": errors,
            "estimatedCalls": total["estimated"], "byModel": by_model, "byStage": by_stage}


def chat_cost(chat_id: str) -> float:
    r = db.one("SELECT COALESCE(SUM(cost),0) AS c FROM calls WHERE chat_id=?", (chat_id,))
    return float(r["c"]) if r else 0.0
