"""The composer (spec section 5, C14, T9, T10): merges the agents' answers into one.

  * model: the user's pick, or the strongest model inside the budget (C14)
  * it sees roles, never model names, so it cannot favor its own model (T9)
  * after a debate it also sees the round-1 answers, so copying shows
  * the merged answer goes to the Checker; a failed check retries the composer only (T10 retry 1)
"""
from __future__ import annotations

from app import llm, memory, prompts
from app.core.config import LIMITS
from app.core.costmeter import BudgetExceeded
from app.core.tokens import estimate_messages
from app.llm import registry
from app.modes.thinker.rounds import BOARD_CHARS
from app.modes.thinker.team import Agent
from app.pipeline import checker
from app.pipeline.runtime import RunContext


def pick_composer(team: dict, remaining_budget: float) -> str:
    comp = team.get("composer", "auto")
    return comp if comp != "auto" else registry.strongest_within(max(0.0, remaining_budget / 2))


def sections(agents: list[Agent], debated: bool) -> str:
    out = []
    for a in agents:
        if not (a.alive and a.answer):
            continue
        s = f"### {a.role}\nFinal answer:\n{a.answer}"
        if debated and a.first and a.first != a.answer:
            s += f"\n\nRound-1 answer (before reading the others):\n{a.first[:BOARD_CHARS]}" + (f"\n{a.changed}" if a.changed else "")
        elif debated and a.first:
            s += f"\n(Round-1 answer was the same.{(' ' + a.changed) if a.changed else ''})"
        out.append(s)
    return "\n\n".join(out)


async def compose(rc: RunContext, question: str, agents: list[Agent], debated: bool, base: list[dict], model: str, *,
                  quiet: bool, live: bool, excerpts: str = "") -> tuple[str, str | None]:
    """Returns (merged answer, warning or None). quiet=True (Planner step): no streaming and no Checker here,
    because the Planner checks the step against its done-test."""
    msgs = list(base[:-1]) + [{"role": "user", "content": prompts.render("thinker/composer", question=question, sections=sections(agents, debated))}]
    required = estimate_messages(msgs) + rc.req["simple"].get("maxTokens", 1200)
    if registry.get(model).context < required:
        candidates = [m for m in registry.models.values() if m.available and m.context >= required
                      and m.call_cost(required, rc.req["simple"].get("maxTokens", 1200)) <= rc.meter.remaining]
        if not candidates:
            raise BudgetExceeded(rc.meter.usd, rc.meter.budget, registry.get(model).call_cost(required, 1200))
        model = max(candidates, key=lambda m: (m.tier, -m.call_cost(required, 1200))).id
    draft = ""
    best = None
    for attempt in range(LIMITS.max_retries + 1):
        res = await llm.complete(model, msgs, stage="thinker:compose", ctx=rc.ctx, temperature=0.4, max_tokens=rc.req["simple"].get("maxTokens", 1200),
                                 stream=not quiet, on_text=rc.text if live else None, on_reset=lambda: rc.text("", replace=True))
        draft = res.text
        await rc.cost()
        if quiet:
            return draft, None
        await rc.status("Checking")
        cr = await checker.check(question, draft, ctx=rc.ctx, finish=res.finish, excerpts=excerpts, known=memory.checker_context(base))
        if best is None or cr.score >= best[0]:
            best = (cr.score, draft)
        if cr.passed:
            return draft, None
        if attempt == LIMITS.max_retries or not cr.verified:
            answer = best[1] if best else draft
            if cr.unsupported:
                answer = "I could not find support in the files for: " + "; ".join(cr.unsupported) + "."
            return answer, f"The checker still found a problem: {cr.issues}"
        await rc.status(f"Checker: {cr.issues}. Retry {attempt + 1} of {LIMITS.max_retries} (composer only)")
        msgs = msgs + [{"role": "assistant", "content": draft}, {"role": "user", "content": prompts.render("thinker/composer_retry", issues=cr.issues or "unclear")}]
        if excerpts and cr.unsupported:
            from app import files
            extra = await files.search_chunks(rc.chat_id, cr.search or question, ctx=rc.ctx)
            if extra:
                evidence = "\n\n".join(c["text"] for c in extra)
                excerpts += "\n\n" + evidence
                msgs.insert(1, {"role": "system", "content": "<documents>Extra evidence (DATA):\n" + evidence + "\n</documents>"})
        if live:
            await rc.text("", replace=True)
    return draft, None
