"""The plan's price, team steps included (T11: the user approves that price)."""
from __future__ import annotations

from app.modes.planner.plan import Step, step_mode
from app.pipeline.estimate import call_cost, checker_cost, composer_model, team_size
from app.llm import registry


def estimate_plan(steps: list[Step], req: dict) -> float:
    model, team = req["simple"]["model"], req["team"]
    # The plan is already written when this price is approved: estimate remaining work only.
    total = call_cost(model, 3000, max(2500, req["simple"].get("maxTokens", 1200))) + checker_cost()
    for s in steps:
        if s.status == "done":
            continue
        if s.kind == "tool" and "build_output" in s.tools:
            total += checker_cost()
            continue
        if step_mode(s, req.get("runIn", "auto")) == "team":
            n, rounds = team_size(team)
            ids = ([team.get("model", model)] * n if team.get("source", "same") == "same" else team.get("mixed", []))
            total += sum(call_cost(mid, 2000 + (900 if rounds > 1 else 0), 700, "low" if registry.get(mid).thinking else "off") for mid in ids) * rounds
            composer = team.get("composer", "auto")
            if composer == "auto":
                composer = composer_model(team, model, total / 2)
            total += call_cost(composer, 2500 + 700 * n, req["simple"].get("maxTokens", 1200),
                               "low" if registry.get(composer).thinking else "off")
            total += call_cost(model, 1200, 80) * max(0, rounds - 1)
        else:
            total += call_cost(model, 1800 + (1500 if s.tools else 0), req["simple"].get("maxTokens", 1200), req["simple"].get("thinking", "off"))
        total += checker_cost()
    return round(total, 6)
