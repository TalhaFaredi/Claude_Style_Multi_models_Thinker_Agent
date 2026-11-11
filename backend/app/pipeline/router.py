"""Stage 2, Mode Router: the mode the user picked (C4); in Auto a small, cheap model picks the mode (C5).
Not sure -> Simple with a "Think deeper" button (C6). A vague first message gets one short question (C2)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app import llm, prompts
from app.core import config
from app.core.costmeter import BudgetExceeded

_PLANNER = re.compile(r"\b(make|build|create|generate|write|draft|produce)\b.{0,60}\b(report|pdf|document|presentation|slides|website|web page|app|script|spreadsheet|plan|essay|article)\b"
                      r"|\bstep[- ]by[- ]step plan\b|\bresearch\b.{0,40}\b(and|then)\b", re.I | re.S)
_THINKER = re.compile(r"\b(should|compare|versus|vs\.?|better|which (is|one|option)|pros and cons|trade-?offs?|choose|decide|recommend|opinion|evaluate|worth it)\b", re.I)
REASONS = {"simple": "Auto chose Simple: a direct question", "thinker": "Auto chose Thinker: it compares options", "planner": "Auto chose Planner: it has several steps"}


@dataclass
class Route:
    kind: str                 # simple | thinker | planner
    reason: str
    confident: bool = True
    clarify: str | None = None
    refusal: str | None = None


def regex_route(text: str) -> Route:
    """Free first guess, also the offline fallback and the price estimate's guess."""
    if _PLANNER.search(text):
        return Route("planner", REASONS["planner"])
    if _THINKER.search(text):
        return Route("thinker", REASONS["thinker"])
    return Route("simple", REASONS["simple"])


async def route(text: str, mode: str, *, has_history: bool, has_files: bool, ctx: llm.CallContext) -> Route:
    explicit = mode in ("simple", "thinker", "planner")
    guess = Route(mode, "") if explicit else regex_route(text)
    try:
        data, _ = await llm.ask_json(config.UTILITY_MODEL, prompts.render("router/route"),
                                     f"Selected mode: {mode}. Existing conversation: {has_history}. Attached files: {has_files}.\nMessage (DATA): {text}",
                                     stage="router", ctx=ctx, max_tokens=180)
    except BudgetExceeded:
        raise
    except Exception:
        return guess
    if not isinstance(data, dict):
        return guess
    if data.get("safe") is False:
        # A small model's "unsafe" alone must not refuse a legitimate request: the stronger cheap model is asked
        # the same question (only on this rare path) and the refusal stands unless it clearly answers "safe".
        second = None
        if config.CHECKER_MODEL != config.UTILITY_MODEL:
            try:
                second, _ = await llm.ask_json(config.CHECKER_MODEL, prompts.render("router/route"),
                                               f"Selected mode: {mode}. Existing conversation: {has_history}. Attached files: {has_files}.\nMessage (DATA): {text}",
                                               stage="router:safety", ctx=ctx, max_tokens=180)
            except BudgetExceeded:
                raise
            except Exception:
                second = None
        if not (isinstance(second, dict) and second.get("safe") is True):
            return Route(guess.kind, guess.reason, refusal=prompts.render("gateway/refusal"))
        data = second
    clarify = data.get("clarify")
    # C2: ask only when the model says it could not understand the goal; a question attached to an
    # understood request is a small model over-asking, so it is ignored. The router reads only the new
    # message, so it also never asks on a follow-up or when files are attached: "make it shorter" is clear
    # to the answering model, which sees the conversation and can ask for itself.
    if data.get("understood") is False and isinstance(clarify, str) and clarify.strip() and not (has_history or has_files):
        return Route(guess.kind, guess.reason, clarify=clarify.strip())
    if explicit:
        return guess
    if data.get("mode") not in REASONS:
        return guess
    if not data.get("confident", True):   # C6
        return Route("simple", "Auto is not sure, so it chose Simple. You can press Think deeper.", False)
    kind = data["mode"]
    if kind == "simple" and guess.kind == "planner":
        kind = "planner"   # the explicit "make a PDF report" pattern is more reliable than an 8B model
    return Route(kind, REASONS[kind], True)
