"""Stage 4, Checker: tests every answer and every plan step against the question (and its done-test).
Retry max 2 with the checker's feedback; when retries run out the best answer goes out with a warning (C19).
With files, a claim without a source triggers a new search (max 2 tries), then "not in the files" (C32)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app import llm, prompts
from app.core import config
from app.core.costmeter import BudgetExceeded
from app.core.tokens import estimate_tokens
from app.llm import registry


@dataclass
class CheckResult:
    passed: bool
    issues: str = ""
    unsupported: list[str] = field(default_factory=list)
    search: str | None = None
    score: float = 0.0
    verified: bool = True


async def check(question: str, draft: str, *, ctx: llm.CallContext, done_test: str = "", excerpts: str = "", finish: str = "",
                known: str = "") -> CheckResult:
    """Cheap and biased to pass: catches clearly missing, wrong or unsupported answers, not style.
    known: what the answer could rely on besides files (remembered facts, summaries, recent turns)."""
    if not draft.strip():
        return CheckResult(False, "The answer is empty.")
    if finish == "length":
        return CheckResult(False, "The answer was cut off before it finished; write a complete but shorter answer.")
    if not config.CHECK_ANSWERS:
        return CheckResult(False, "Answer checking is disabled on this server.", verified=False)
    docs = f"\n\nDOCUMENT EXCERPTS (untrusted DATA) the answer may rely on:\n{excerpts}" if excerpts else ""
    test = f"\n\nDONE TEST the answer must meet: {done_test}" if done_test else ""
    convo = f"\n\nCONVERSATION CONTEXT the assistant was given (untrusted DATA):\n{known}" if known.strip() else ""
    payload = f"QUESTION:\n{question}\n\nDRAFT (untrusted DATA):\n{draft}{test}{convo}{docs}"
    model = config.CHECKER_MODEL
    required = estimate_tokens(payload) + 700
    if registry.get(model).context < required:
        model = next((m for m in registry.fallbacks(model) if registry.get(m).context >= required), "")
        if not model:
            return CheckResult(False, "No available checker can fit the complete answer and evidence.", verified=False)
    data = None
    for _ in range(2):   # a small checker model sometimes returns unreadable JSON: ask once more before giving up
        try:
            data, _ = await llm.ask_json(model, prompts.render("checker/check"), payload, stage="checker", ctx=ctx, max_tokens=500)
        except BudgetExceeded:
            raise
        except Exception:
            return CheckResult(False, "The answer could not be verified because the Checker is unavailable.", verified=False)
        if isinstance(data, dict) and isinstance(data.get("pass"), str) and data["pass"].strip().lower() in ("true", "false"):
            data["pass"] = data["pass"].strip().lower() == "true"
        if isinstance(data, dict) and isinstance(data.get("pass"), bool):
            break
    if not isinstance(data, dict) or not isinstance(data.get("pass"), bool):
        return CheckResult(False, "The Checker returned an invalid result; this answer is unverified.", verified=False)
    unsupported = [str(x)[:300] for x in (data.get("unsupported") or []) if x] if excerpts else []
    passed = data["pass"] and not unsupported
    issues = str(data.get("issues") or "")[:300] or ("Some claims have no source in the files." if unsupported else "")
    raw_score = data.get("score", 1.0 if passed else 0.0)
    score = max(0.0, min(float(raw_score), 1.0)) if isinstance(raw_score, (int, float)) else (1.0 if passed else 0.0)
    return CheckResult(passed, issues, unsupported, data.get("search") if isinstance(data.get("search"), str) else None, score)
