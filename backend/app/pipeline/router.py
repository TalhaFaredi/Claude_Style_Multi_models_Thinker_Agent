"""Stage 2, input check: the user always picks the mode (Simple, Thinker or Planner), so nothing is "routed" any more.
A small, cheap helper model only screens the message before the chosen mode runs:

  * safety: clearly disallowed requests are refused (confirmed by a second, stronger cheap model);
  * clarity (C2): before an expensive Thinker or Planner run, a message whose goal cannot be understood gets ONE
    short question instead. Simple never does this: the model the user chose answers every message itself,
    so the answer (and its cost) always come from that model.

Set INPUT_CHECK=0 to skip the helper call entirely (the deny-list in gateway.py still runs).
"""
from __future__ import annotations

from dataclasses import dataclass

from app import llm, prompts
from app.core import config
from app.core.costmeter import BudgetExceeded

MODES = ("simple", "thinker", "planner")


@dataclass
class Route:
    kind: str                 # simple | thinker | planner: always the mode the user selected
    reason: str = ""
    confident: bool = True
    clarify: str | None = None
    refusal: str | None = None


async def route(text: str, mode: str, *, has_history: bool, has_files: bool, ctx: llm.CallContext) -> Route:
    kind = mode if mode in MODES else "simple"
    chosen = Route(kind)
    if not config.INPUT_CHECK:
        return chosen
    question = f"Selected mode: {kind}. Existing conversation: {has_history}. Attached files: {has_files}.\nMessage (DATA): {text}"
    try:
        data, _ = await llm.ask_json(config.UTILITY_MODEL, prompts.render("router/route"), question, stage="router", ctx=ctx, max_tokens=120)
    except BudgetExceeded:
        raise
    except Exception:
        return chosen   # the helper being down must never block the user's own model
    if not isinstance(data, dict):
        return chosen
    if data.get("safe") is False:
        # A small model's "unsafe" alone must not refuse a legitimate request: the stronger cheap model is asked
        # the same question (only on this rare path) and the refusal stands unless it clearly answers "safe".
        second = None
        if config.CHECKER_MODEL != config.UTILITY_MODEL:
            try:
                second, _ = await llm.ask_json(config.CHECKER_MODEL, prompts.render("router/route"), question, stage="router:safety", ctx=ctx, max_tokens=120)
            except BudgetExceeded:
                raise
            except Exception:
                second = None
        if not (isinstance(second, dict) and second.get("safe") is True):
            return Route(kind, refusal=prompts.render("gateway/refusal"))
        data = second
    clarify = data.get("clarify")
    # C2: ask only when the helper says it could not understand the goal; a question attached to an understood
    # request is a small model over-asking, so it is ignored. The helper reads only the new message, so it never
    # asks on a follow-up or when files are attached. And never in Simple: there the chosen model answers.
    if (kind != "simple" and data.get("understood") is False and isinstance(clarify, str) and clarify.strip()
            and not (has_history or has_files)):
        return Route(kind, clarify=clarify.strip())
    return chosen
