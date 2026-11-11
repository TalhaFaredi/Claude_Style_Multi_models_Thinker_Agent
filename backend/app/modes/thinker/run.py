"""Mode B: Thinker (spec section 5, Figure 3; team cases in section 7).

  1. build the team (same model with roles, or different models)        team.py
  2. gather facts once for the whole team if web search is on (T4)
  3. round 1: everyone answers alone                                       rounds.py
  4. together style: judge -> stop if they agree (T7), else read the board and revise (max 3 rounds)
  5. fewer than 2 answers -> fall back to Simple (C13)
  6. composer merges -> Checker -> retry composer only (T10)              composer.py
The same code runs Planner team steps (quiet=True: progress goes to the plan card, no streaming).
"""
from __future__ import annotations

from typing import Awaitable, Callable

from app import memory, skills, tools
from app.core.config import LIMITS, SKILLS_BUDGET
from app.core.costmeter import BudgetExceeded
from app.llm import registry
from app.modes.common import Result, emit_buffered, skills_note, stream_now
from app.modes.simple import run_simple
from app.modes.thinker.composer import compose, pick_composer
from app.modes.thinker.rounds import agree, board_for, round_cost, run_round, split_change
from app.modes.thinker.team import Agent, Progress, build_agents, tier_warning
from app.pipeline.runtime import RunContext


async def _gather_once(rc: RunContext, text: str) -> tuple[str, list[str]]:
    """T4: run the search one time and give every agent the same facts."""
    await rc.status("Gathering facts once for the whole team")
    r = await tools.execute("web_search", {"query": text[:160]}, rc.tools, allowed={"web_search"})
    if r.ok and "<web_results>" in r.text:
        await rc.emit({"type": "tool", "state": "done", "label": r.done_label})
        return r.text, r.citations
    return "", []


async def run_thinker(rc: RunContext, text: str, *, quiet: bool = False, on_note: Callable[[str], Awaitable[None]] | None = None,
                      reuse: list[Agent] | None = None, force_web: bool = False) -> Result:
    """quiet: a Planner team step. reuse: the agents of the previous try, for a composer-only retry (T10)."""
    team = rc.req["team"]
    progress = Progress(rc, quiet, on_note)
    agents = reuse if reuse is not None else build_agents(team)
    same = team.get("source", "same") == "same"
    style = team.get("style", "independent")
    rounds = max(LIMITS.min_rounds, min(int(team.get("rounds", 2)), LIMITS.max_rounds)) if style == "together" else 1
    if len(agents) < LIMITS.min_agents:   # C13
        await rc.status("Fewer than 2 agents: answering in Simple mode")
        return await run_simple(rc, text, model_id=agents[0].model if agents else None)
    if not same and (warn := tier_warning(agents)):
        await rc.warn(warn + " Pick models from the same strength tier for a more reliable team.")

    want_web = force_web if quiet else bool(rc.req["simple"].get("tools", {}).get("web"))
    if "shared_facts" not in rc.team_cache:
        rc.team_cache["shared_facts"] = await _gather_once(rc, text) if want_web else ("", [])
    extra, cites = rc.team_cache["shared_facts"]
    chosen_skills = skills.select(text, mode="thinker", budget_tokens=int(rc.settings.get("windowCap", 32000) * SKILLS_BUDGET))
    if not quiet:
        await skills_note(rc, [s.name for s in chosen_skills])
    if reuse is not None and "built" in rc.team_cache:
        built = rc.team_cache["built"]
    else:
        smallest = min((a.model for a in agents), key=lambda mid: registry.get(mid).context)
        built = await memory.build(rc.chat_id, text, smallest, ctx=rc.ctx, skills_text=skills.render(chosen_skills),
                                   images_ok=all(registry.get(a.model).vision for a in agents))
        rc.team_cache["built"] = built
    rc.evidence = built.files.text if built.files else ""
    if not quiet:
        await rc.status("Agents thinking")
        notes = ["Same question to every agent, each with its own role." if same else "Different models answer the same question.",
                 "Together: agents read the shared board and revise." if style == "together" else "On their own: nobody sees the others."]
        await rc.emit({"type": "thinking", "notes": notes + (["A judge checks if the main conclusions match."] if style == "together" else [])})

    debated = bool(rc.team_cache.get("debated", False)) if reuse is not None else False
    try:
        if reuse is None:
            label = f"Round 1 of {rounds}: each thinks alone" if style == "together" else "Thinking on their own"
            if await run_round(rc, progress, agents, built.messages, extra, None, same, label) < LIMITS.min_agents:   # C13
                await rc.status("Fewer than 2 agents answered: answering in Simple mode")
                return await run_simple(rc, text)
            for r in range(2, rounds + 1):
                if await agree(rc, text, agents):   # T7
                    await progress.push(agents, "They agree on the main point")
                    break
                est = round_cost(agents, built.tokens + 1600) + registry.get(agents[0].model).call_cost(3000, 800)
                if rc.meter.usd + est > rc.meter.budget:   # Budget Guard: skip the debate rather than overspend
                    await rc.status("Budget is tight: skipping the remaining debate rounds")
                    break
                boards = {i: board_for(agents, i) for i in range(len(agents))}
                count = await run_round(rc, progress, agents, built.messages, extra, boards, same, f"Round {r} of {rounds}: reading each other, revising")
                if count < LIMITS.min_agents:
                    await rc.status("Fewer than 2 agents answered: answering in Simple mode")
                    return await run_simple(rc, text)
                debated = True
                rc.team_cache["debated"] = True
                for a in agents:   # T8: an agent that changes its answer must say why
                    if a.alive and a.answer:
                        a.changed, a.answer = split_change(a.answer)
                if r == rounds:
                    await progress.push(agents, "They agree on the main point" if await agree(rc, text, agents) else "Rounds finished")
    except BudgetExceeded:
        if not any(a.alive and a.answer for a in agents):
            raise
        await rc.warn("The budget ran out during the debate; the answer uses what the agents had finished.")

    if sum(a.alive and bool(a.answer) for a in agents) < LIMITS.min_agents:
        return await run_simple(rc, text)

    comp_model = pick_composer(team, rc.meter.remaining)
    if not quiet:
        await rc.status("Composing")
    await progress.push(agents, "Composer is writing the answer")
    live = stream_now() and not quiet
    if not quiet:
        await rc.emit({"type": "composer", "model": registry.get(comp_model).name, "status": "running", "explanation": "Merging agreement, resolving conflicts and checking the final answer."})
    draft, warning = await compose(rc, text, agents, debated, built.messages, comp_model, quiet=quiet, live=live, excerpts=rc.evidence)
    if not live and not quiet:
        await emit_buffered(rc, draft)
    await progress.push(agents, "Done")
    if not quiet:
        await rc.emit({"type": "composer", "model": registry.get(comp_model).name, "status": "done", "explanation": "Merged the independent role-labelled answers and checked the result." if not warning else warning})
    if cites and not quiet:
        await rc.emit({"type": "citations", "items": cites})
    return Result(draft, cites, warning, comp_model, extra=agents)
