"""Cost estimate before the run ("cost estimate before the run, budget guard during the run").
Built from real registry prices and the real size of this chat's context, so it moves as the chat grows.
The Budget Guard in app/core/costmeter.py enforces the budget during the run."""
from __future__ import annotations

from app import memory
from app.core import config
from app.core.config import LIMITS
from app.llm import registry
from app.pipeline.router import MODES

THINK_OUT = {"off": 0, "low": 1024, "medium": 2048, "high": 4096}


def call_cost(model_id: str, tin: int, tout: int, thinking: str = "off", cached: int = 0) -> float:
    m = registry.get(model_id)
    return m.call_cost(tin, tout + (THINK_OUT.get(thinking, 0) if m.thinking else 0), cached)


def checker_cost() -> float:
    return call_cost(config.CHECKER_MODEL, 1100, 90)


def composer_model(team: dict, default: str, allowance: float = 0.01) -> str:
    """Estimation must report an expensive/unavailable choice rather than raise a spend guard."""
    selected = team.get("composer", "auto")
    if selected != "auto":
        return selected
    available = [m for m in registry.models.values() if m.available and m.featured and m.price_known]
    affordable = [m for m in available if m.call_cost() <= max(0.0, allowance)]
    if affordable:
        return max(affordable, key=lambda m: (m.tier, -m.call_cost())).id
    return min(available, key=lambda m: m.call_cost()).id if available else default


def team_size(team: dict) -> tuple[int, int]:
    """(agents, rounds) after the fixed limits."""
    n = team.get("agents", 3) if team.get("source", "same") == "same" else len(team.get("mixed") or [])
    n = max(LIMITS.min_agents, min(n, LIMITS.max_agents))
    rounds = team.get("rounds", 2) if team.get("style") == "together" else 1
    return n, max(1, min(rounds, LIMITS.max_rounds))


async def estimate(req: dict, chat_id: str | None) -> dict:
    """req: {mode, simple:{model,thinking,tools}, team:{...}, runIn, prompt}. Returns {usd, calls, breakdown, kind}."""
    mode = req.get("mode") if req.get("mode") in MODES else "simple"
    simple, team = req.get("simple") or {}, req.get("team") or {}
    model = simple.get("model") or config.UTILITY_MODEL
    thinking = simple.get("thinking", "off")
    max_tokens = simple.get("maxTokens", 1200)
    used = 600
    if chat_id and memory.get_chat(chat_id):
        used = max(600, (await memory.meter(chat_id, model))["usedTokens"])
    prompt_tokens = max(20, len(req.get("prompt") or "") // 4)
    tools_on = bool((simple.get("tools") or {}).get("web")) and registry.get(model).tools
    kind = mode

    parts: dict[str, float] = {}
    calls = 0
    if config.INPUT_CHECK:
        parts["input check"] = call_cost(config.UTILITY_MODEL, prompt_tokens + 400, 120)
        calls += 1
    if kind == "simple":
        c = call_cost(model, used + prompt_tokens, max_tokens, thinking)
        if tools_on:
            c += call_cost(model, used + prompt_tokens + 1800, max_tokens, thinking)
        parts["answer"] = c + checker_cost()
        calls += 2 + (1 if tools_on else 0)
    elif kind == "thinker":
        n, rounds = team_size(team)
        lean = min(used, 2500) + prompt_tokens
        ids = [team.get("model", model)] * n if team.get("source", "same") == "same" else (team.get("mixed") or [model] * n)
        parts["agents"] = sum(call_cost(i, used + prompt_tokens + 150, 700, "low" if registry.get(i).thinking else "off") for i in ids) + sum(call_cost(i, used + prompt_tokens + 950, 700, "low" if registry.get(i).thinking else "off") for i in ids) * (rounds - 1)
        calls += n * rounds
        if rounds > 1:
            parts["judge"] = call_cost(config.UTILITY_MODEL, 1200, 60) * (rounds - 1)
            calls += rounds - 1
        comp = composer_model(team, model)
        parts["composer"] = call_cost(comp, 700 * n + used + prompt_tokens, max_tokens,
                                       "low" if registry.get(comp).thinking else "off")
        parts["checker"] = checker_cost()
        calls += 2
    else:   # planner: a typical 4-step plan
        run_in, steps = req.get("runIn", "auto"), 4
        parts["plan"] = call_cost(req.get("planModel") or model, used // 2 + 500, 1100)
        hard = steps - 1 if run_in == "thinker" else (1 if run_in == "auto" else 0)
        easy = steps - hard
        parts["steps"] = (call_cost(model, 1800, 600, thinking) + checker_cost()) * easy
        calls += 1 + 2 * easy
        if hard:
            n, rounds = team_size(team)
            ids = [team.get("model", model)] * n if team.get("source", "same") == "same" else team.get("mixed", [])
            comp = composer_model(team, model)
            parts["team steps"] = hard * (sum(call_cost(mid, 2000, 700, "low" if registry.get(mid).thinking else "off") for mid in ids) * rounds
                                           + call_cost(comp, 2500, max_tokens, "low" if registry.get(comp).thinking else "off") + checker_cost())
            calls += hard * (n * rounds + 2)
        parts["output"] = call_cost(model, 3000, max(2500, max_tokens)) + checker_cost()
        calls += 2
    if memory.get_settings()["longMemory"]:
        parts["memory"] = call_cost(config.WRITER_MODEL, 1800, 500) * 2
        calls += 2
    return {"usd": round(sum(parts.values()), 6), "calls": calls, "breakdown": {k: round(v, 6) for k, v in parts.items()}, "kind": kind}
