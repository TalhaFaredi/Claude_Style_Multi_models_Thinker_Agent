"""Bounded Planner: versioned approval, durable steps, checked retries and re-plans."""
from __future__ import annotations

import asyncio

from app.core.config import LIMITS
from app.core.costmeter import BudgetExceeded, usd
from app.modes.common import Result
from app.modes.planner.assemble import assemble
from app.modes.planner.estimate import estimate_plan
from app.modes.planner.plan import Step, make_plan
from app.modes.planner.steps import emit_plan, run_step
from app.pipeline.runtime import RunContext

MAX_PLAN_EDITS = 5


async def wait_approval(rc: RunContext) -> tuple[str, str]:
    while True:
        item = await rc.approvals.get()
        kind, note = item[:2]
        if len(item) > 2 and item[2] != rc.approval_version:
            continue
        if kind in ("approve", "cancel", "edit"):
            rc.awaiting_approval = False
            return kind, note


def _set_status(steps: list[Step], status: str) -> None:
    for s in steps:
        if s.status != "done":
            s.status = status


async def _approve(rc: RunContext, goal: str, steps: list[Step], meta: dict) -> tuple[list[Step], dict]:
    edits = 0
    while True:
        rc.plan_steps[:] = steps
        rc.plan_meta = meta
        _set_status(steps, "planned")
        price = estimate_plan(steps, rc.req)
        rc.begin_approval()
        await emit_plan(rc, steps, "Waiting for your approval", awaiting=True, estimate=price)
        if price > rc.meter.remaining:
            await rc.warn(f"The remaining plan is estimated at {usd(price)}, above {usd(rc.meter.remaining)} remaining. Edit for fewer team steps, agents or rounds, or a cheaper model.")
        kind, note = await wait_approval(rc)
        if kind == "cancel":
            raise asyncio.CancelledError()
        if kind == "approve":
            if price > rc.meter.remaining:
                await rc.warn("This plan exceeds the approved budget. Make it cheaper before approving.")
                continue
            return steps, meta
        if edits >= MAX_PLAN_EDITS:
            await rc.warn("The plan edit limit is reached. Review and approve this plan, or cancel and start a new question. Nothing has run.")
            continue
        edits += 1
        if any(word in note.lower() for word in ("cheaper", "fewer agents", "one round")):
            rc.req["team"].update(agents=2, rounds=1)
            rc.req["team"]["mixed"] = rc.req["team"].get("mixed", [])[:2]
            note += " Use Simple for every easy/tool step; minimize paid calls and fit the approved budget."
        await rc.status("Re-writing the plan")
        kept = [s for s in steps if s.status == "done"]
        new_steps, new_meta = await make_plan(rc, goal, note=note, done=kept)
        steps, meta = kept + new_steps, {**meta, **new_meta}


async def _replan(rc: RunContext, goal: str, steps: list[Step], meta: dict, failed: int) -> tuple[list[Step], dict]:
    kept = [s for s in steps if s.status == "done"]
    reason = f"{steps[failed].task}: {steps[failed].note}"
    new_steps, new_meta = await make_plan(rc, goal, done=kept, failed=reason)
    # Every replacement plan is reviewable; no goal-change heuristic bypasses approval.
    steps, meta = await _approve(rc, goal, kept + new_steps, {**meta, **new_meta})
    _set_status(steps, "waiting")
    await emit_plan(rc, steps, "Running")
    return steps, meta


async def run_planner(rc: RunContext, goal: str) -> Result:
    await rc.emit({"type": "plan", "phase": "Writing the plan", "steps": [], "awaitingApproval": False, "estimateUsd": None})
    steps, meta = await make_plan(rc, goal)
    steps, meta = await _approve(rc, goal, steps, meta)
    rc.plan_steps[:] = steps
    _set_status(steps, "waiting")
    await emit_plan(rc, steps, "Running")
    sources: set[str] = set()
    replans, loops, stopped = 0, 0, ""
    while any(s.status in ("waiting", "retry") for s in steps):
        loops += 1
        if loops > LIMITS.max_plan_steps * (LIMITS.max_retries + 2) or len(steps) > LIMITS.max_plan_steps:
            stopped = "plan or loop limit reached"
            break
        if rc.remaining_time() <= 0:
            stopped = "time limit reached"
            break
        ready = [i for i, s in enumerate(steps) if s.status == "waiting" and all(steps[n].status == "done" for n in s.needs)]
        if not ready:
            stopped = "a required step did not finish"
            break
        batch = ready[:LIMITS.max_parallel_steps]
        results = await asyncio.gather(*(run_step(rc, goal, steps, i, sources) for i in batch), return_exceptions=True)
        for r in results:
            if isinstance(r, (BudgetExceeded, asyncio.CancelledError)):
                raise r
        failed = [i for i, r in zip(batch, results) if r is not True]
        for i, r in zip(batch, results):
            if r is not True and steps[i].status != "failed":
                steps[i].status, steps[i].note, steps[i].tone = "failed", f"Error: {r}"[:300], "warn"
        if not failed:
            continue
        offers = [i for i in failed if rc.req.get("runIn") == "simple" and steps[i].kind != "tool" and not steps[i].use_team]
        if offers:
            await emit_plan(rc, steps, "A step failed. Use the team to retry, or cancel.")
            selected = await asyncio.wait_for(rc.team_requests.get(), max(0.1, rc.remaining_time()))
            if selected in offers:
                steps[selected].use_team, steps[selected].status = True, "waiting"
                if all(i == selected for i in failed):
                    continue
                failed = [i for i in failed if i != selected]
        if replans >= LIMITS.max_replans:
            stopped = f"step {failed[0] + 1} failed after two retries and two re-plans"
            await rc.emit({"type": "clarify", "question": "The re-plan limit is reached. Would you like to change the goal or try a different model in a new question?"})
            break
        replans += 1
        await rc.status(f"Re-planning the remaining steps ({replans} of {LIMITS.max_replans})")
        steps, meta = await _replan(rc, goal, steps, meta, failed[0])
        rc.plan_steps[:] = steps

    if stopped:
        await rc.warn(f"Stopped: {stopped}. Completed work and remaining steps are saved.")
        await emit_plan(rc, steps, "Stopped with partial result")
        return Result(rc.partial_text(stopped), sorted(sources), stopped, partial=True)
    if not any(s.result for s in steps):
        return Result("No step finished. Review the goal and try a new plan.", warning="No deliverable was produced.", partial=True)
    result = await assemble(rc, goal, steps, meta, sources)
    await emit_plan(rc, steps, "Finished")
    return result
