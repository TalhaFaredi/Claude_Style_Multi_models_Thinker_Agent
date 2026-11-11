"""Thinking rounds (spec section 5 and team rules T6 to T8).

Round 1: every agent answers alone, all at the same time.
Together style, rounds 2..R: each agent reads the others' latest short answers on a shared board and revises;
an agent that changes its answer must say why. A cheap judge checks after each round; if all agree, the
remaining rounds are skipped (T7). A failed agent is dropped (same model) or replaced by the next similar
model (different models) (T6).
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import replace

from app import llm, prompts
from app.core import config
from app.core.costmeter import BudgetExceeded
from app.llm import registry
from app.modes.thinker.team import Agent, Progress
from app.pipeline.runtime import RunContext

BOARD_CHARS = 1200   # the board keeps only each agent's latest short answer, so it does not fill the window
AGENT_MAX_TOKENS = 700


def excerpt(answer: str, limit: int = BOARD_CHARS) -> str:
    """A long answer cut to `limit` characters, keeping its start AND its end. Every role is told to finish with
    its own best answer, so a head-only cut showed the judge and the board the lead-in, not the conclusion."""
    if len(answer) <= limit:
        return answer
    head = limit // 3
    return f"{answer[:head]}\n[...]\n{answer[-(limit - head):]}"


def _messages_for(base: list[dict], agent: Agent, extra_system: str, board: str | None) -> list[dict]:
    msgs = [dict(m) for m in base]
    msgs[0] = {"role": "system", "content": msgs[0]["content"] + "\n\n" + prompts.render("thinker/agent", role=agent.role_prompt())}
    if extra_system:   # T4: facts gathered once for the whole team
        msgs.insert(1, {"role": "system", "content": extra_system})
    if board:
        # A revising agent is asked whether (and why) it changed, so it must see its own earlier answer. It used
        # to get only the others' answers glued to the question, which also dropped any attached images.
        msgs += [{"role": "assistant", "content": agent.answer or "(no earlier answer)"}, {"role": "user", "content": board}]
    return msgs


async def _agent_answer(rc: RunContext, agent: Agent, base: list[dict], extra: str, board: str | None, same: bool, team_models: set[str]) -> str:
    original_model = agent.model
    messages = _messages_for(base, agent, extra, board)
    # A capable model gets a bounded low reasoning allowance. The client reserves those tokens separately
    # from AGENT_MAX_TOKENS, so the agent still has room for a visible answer.
    thinking = "low" if registry.get(agent.model).thinking else "off"
    agent_ctx = replace(rc.ctx, label=agent.role)
    res = await llm.complete(agent.model, messages, stage="thinker:agent", ctx=agent_ctx, temperature=agent.temp,
                             max_tokens=AGENT_MAX_TOKENS, thinking=thinking, allow_fallback=not same, exclude=team_models)
    if not res.text.strip():
        raise ValueError("The agent returned an empty answer")   # T6: counts as a failed agent, visibly
    if not same:
        if res.model != original_model and res.model in team_models:
            raise ValueError("A replacement model is already in this team")
        team_models.add(res.model)
        agent.model = res.model   # T6: a different model stood in for a failed one
    answer = res.text.strip()
    if board and re.fullmatch(r"unchanged\.?", answer, re.I):
        return agent.answer   # "Unchanged" alone: the earlier answer stands, with no extra paid call
    if board and answer != agent.answer:
        change, _ = split_change(answer)
        if not change:
            messages += [{"role": "assistant", "content": answer}, {"role": "user", "content": "Explain the change compared with your previous answer. Begin with 'Changed because: ...' or 'Unchanged', then a blank line and your complete answer."}]
            amended = await llm.complete(agent.model, messages, stage="thinker:change", ctx=agent_ctx, temperature=0.2,
                                         max_tokens=AGENT_MAX_TOKENS, thinking="low" if registry.get(agent.model).thinking else "off",
                                         allow_fallback=not same, exclude=team_models)
            if not split_change(amended.text)[0]:
                raise ValueError("Revised answer did not explain its change")
            answer = amended.text.strip()
    return answer


async def run_round(rc: RunContext, progress: Progress, agents: list[Agent], base: list[dict], extra: str, boards: dict[int, str] | None,
                    same: bool, label: str) -> int:
    """All live agents at once. Returns how many have an answer."""
    revising = boards is not None
    team_models = {a.model for a in agents}
    for a in agents:
        a.status = "revising" if revising else "thinking"
    await progress.push(agents, label)

    async def one(i: int, a: Agent):
        try:
            a.answer = await _agent_answer(rc, a, base, extra, (boards or {}).get(i), same, team_models)
            if not revising:
                a.first = a.answer
            a.status = "ready"
            rc.view.setdefault("meta", {}).setdefault("agentResults", {})[a.role] = a.answer
        except BudgetExceeded:
            raise
        except Exception:   # failed after retries and fallbacks: drop this agent (T6)
            if revising and a.answer:
                a.status = "ready"   # a failed revision keeps the answer already paid for, as "unchanged"
            else:
                a.alive = False
        finally:
            await progress.push(agents, label)
            await rc.cost()

    results = await asyncio.gather(*(one(i, a) for i, a in enumerate(agents) if a.alive), return_exceptions=True)
    for r in results:
        if isinstance(r, BudgetExceeded):
            raise r
    return sum(1 for a in agents if a.alive and a.answer)


def board_for(agents: list[Agent], me: int) -> str:
    lines = [f"[{a.role}] {excerpt(a.answer)}" for i, a in enumerate(agents) if a.alive and i != me and a.answer]
    return prompts.render("thinker/board", board="\n\n".join(lines))


def split_change(text: str) -> tuple[str, str]:
    """('Changed because: ...' or 'Unchanged', the answer)."""
    m = re.match(r"\s*(Changed because:.*?|Unchanged\.?)\s*\n+(.*)", text, re.S | re.I)
    return (m.group(1).strip(), m.group(2).strip()) if m else ("", text)


async def agree(rc: RunContext, question: str, agents: list[Agent]) -> bool:
    """The judge: do all answers reach the same main conclusion?"""
    joined = "\n\n".join(f"[{a.role}] {excerpt(a.answer, 900)}" for a in agents if a.alive and a.answer)
    try:
        # 40 tokens: a cut-off {"agree":true} cannot be read, counts as "disagree" and buys a whole extra round.
        data, _ = await llm.ask_json(config.UTILITY_MODEL, prompts.render("thinker/judge"), f"QUESTION: {question[:400]}\n\n{joined}",
                                     stage="thinker:judge", ctx=rc.ctx, max_tokens=40)
        return bool(isinstance(data, dict) and data.get("agree"))
    except BudgetExceeded:
        raise
    except Exception:
        return False


def round_cost(agents: list[Agent], context_tokens: int) -> float:
    return sum(registry.get(a.model).call_cost(context_tokens, 600) for a in agents if a.alive)
