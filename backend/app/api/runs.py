"""Runs: start a question (streams events), Planner approve / edit, Stop, rating."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app import memory
from app.api.common import sse
from app.api.schemas import ApprovalRequest, EditRequest, PermissionRequest, RatingRequest, RunRequest, TeamStepRequest
from app.pipeline.engine import manager

router = APIRouter()


def _run(run_id: str):
    run = manager.get(run_id)
    if not run or run.finished:
        raise HTTPException(404, "Unknown or finished run")
    return run


@router.post("/api/runs")
async def create_run(body: RunRequest):
    existing = manager.get(body.id)
    if existing and not existing.finished:
        raise HTTPException(409, "This run is already in progress")
    req = body.model_dump()
    req["team"] = body.team.clamped()
    try:
        run = await manager.start(req)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return sse(run.rc.queue)


@router.post("/api/runs/{run_id}/approve")
async def approve(run_id: str, body: ApprovalRequest | None = None):
    rc = _run(run_id).rc
    if (rc.view.get("plan") or {}).get("overBudget"):
        raise HTTPException(402, "Make this plan cheaper before approving it; its estimate exceeds the remaining budget.")
    await _approval(rc, body.planVersion if body else None)
    await rc.approvals.put(("approve", "", rc.approval_version))
    return {"ok": True}


@router.post("/api/runs/{run_id}/edit")
async def edit_plan(run_id: str, body: EditRequest):
    rc = _run(run_id).rc
    await _approval(rc, body.planVersion)
    await rc.approvals.put(("edit", body.note, rc.approval_version))
    return {"ok": True}


async def _approval(rc, version: str | None) -> None:
    if not rc.awaiting_approval:
        raise HTTPException(409, "This run is not waiting for plan approval")
    if not version or version != rc.approval_version:
        if rc.view.get("plan"):
            await rc.emit({"type": "plan", **rc.view["plan"]})
        raise HTTPException(409, "The plan changed. Review the current plan before approving.")
    # Consume the gate at receipt, preventing duplicate clicks/queued approvals.
    rc.awaiting_approval = False


@router.post("/api/runs/{run_id}/permission")
async def permission(run_id: str, body: PermissionRequest):
    rc = _run(run_id).rc
    pending = rc.permissions.get(body.id)
    if pending is None or pending.done():
        raise HTTPException(409, "This permission request has expired")
    pending.set_result(body.allow)
    return {"ok": True}


@router.post("/api/runs/{run_id}/use-team")
async def use_team(run_id: str, body: TeamStepRequest):
    rc = _run(run_id).rc
    if body.step >= len(rc.plan_steps):
        raise HTTPException(404, "Unknown plan step")
    step = rc.plan_steps[body.step]
    if step.status != "failed" or step.kind == "tool" or step.use_team:
        raise HTTPException(409, "This step is not waiting for a team retry")
    step.use_team = True
    await rc.team_requests.put(body.step)
    return {"ok": True}


@router.post("/api/runs/{run_id}/stop")
async def stop(run_id: str):
    run = manager.get(run_id)
    stopped = manager.stop(run_id)
    if stopped and run and run.task:
        await asyncio.shield(run.task)  # settle cancellation charges and persist progress before acknowledging
    return {"stopped": stopped, "usd": round(run.rc.meter.usd, 6) if run else 0,
            "calls": run.rc.meter.calls if run else 0}


@router.post("/api/messages/{message_id}/rating")
async def rate(message_id: str, body: RatingRequest):
    memory.rate_message(message_id, body.value)
    return {"ok": True}
