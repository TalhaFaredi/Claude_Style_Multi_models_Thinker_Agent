"""Per-run state. RunContext carries everything one answer needs (request, budget meters, the event queue to
the browser, the approval queue for the Planner) and keeps a server-side copy of the answer view, saved with
the message so a reloaded chat shows exactly what was streamed.

Events (the wire contract with frontend/src/domain/events.ts):
  route, status, thinking, tool, text, citations, agents, plan, output, cost, context, warning,
  clarify, compact, note, done, error
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.costmeter import CostMeter
from app.llm import CallContext
from app.tools import ToolRun


def fresh_view(kind: str, prompt: str, snapshot: dict, auto: bool) -> dict:
    return {"kind": kind, "prompt": prompt, "auto": auto, "status": "live", "statusText": "Starting", "thinkingNotes": [], "thoughtSeconds": None,
            "tool": None, "text": "", "citations": [], "roundText": "", "agents": [], "plan": None, "output": None, "calls": 0, "costUsd": 0.0,
            "error": None, "warning": None, "composer": None, "permission": None, "snapshot": snapshot, "meta": {}}


def apply_event(v: dict, e: dict) -> None:
    """Python mirror of the frontend reducer (reduceRunEvent.ts). Keep the two in step."""
    t = e["type"]
    if t == "route":
        v["kind"] = e["kind"]
    elif t == "status":
        v["statusText"], v["status"] = e["text"], "live"
    elif t == "thinking":
        v["thinkingNotes"], v["thoughtSeconds"] = e["notes"], e.get("seconds")
    elif t == "tool":
        v["tool"] = {"state": e["state"], "label": e["label"]}
    elif t == "text":
        v["text"] = e["delta"] if e.get("replace") else v["text"] + e["delta"]
    elif t == "citations":
        v["citations"] = e["items"]
    elif t == "agents":
        v["roundText"], v["agents"] = e["roundText"], e["agents"]
    elif t == "plan":
        v["plan"] = {"phase": e["phase"], "steps": e["steps"], "awaitingApproval": e["awaitingApproval"], "estimateUsd": e.get("estimateUsd"), "version": e.get("version"),
                     "overBudget": e.get("overBudget", False), "remainingBudgetUsd": e.get("remainingBudgetUsd")}
        v["status"] = "waiting" if e["awaitingApproval"] else "live"
        v["statusText"] = e["phase"]
    elif t == "output":
        v["output"] = e["file"]
    elif t == "composer":
        v["composer"] = {k: value for k, value in e.items() if k != "type"}
    elif t == "permission":
        v["permission"] = None if e.get("resolved") else {k: value for k, value in e.items() if k != "type"}
        v["status"] = "live" if e.get("resolved") else "waiting"
    elif t == "cost":
        v["calls"], v["costUsd"] = e["calls"], e["usd"]
    elif t == "call_usage":
        v.setdefault("meta", {}).setdefault("callUsages", []).append({k: value for k, value in e.items() if k != "type"})
    elif t == "model_thinking":
        v.setdefault("meta", {}).setdefault("modelThinking", []).append({k: value for k, value in e.items() if k != "type"})
    elif t == "warning":
        v["warning"] = e["message"]
    elif t == "done":
        v["status"], v["statusText"] = "done", "Done"
    elif t == "error":
        v["status"], v["error"] = "error", e["message"]


_SENT = re.compile(r"(?<=[.!?])\s+")


def notes_from_reasoning(text: str, limit: int = 5) -> list[str]:
    """Short reasoning notes for the collapsible "Thought for N seconds" section."""
    sents = [s.strip() for s in _SENT.split(text.replace("\n", " ")) if len(s.strip()) > 12]
    if not sents:
        return []
    step = max(1, len(sents) // limit)
    return [s[:160] for s in sents[::step][:limit]]


@dataclass
class RunContext:
    run_id: str
    chat_id: str
    req: dict
    meter: CostMeter                    # the user's budget for this question
    settings: dict
    queue: "asyncio.Queue[dict | None]"
    view: dict
    deadline: float
    ctx: CallContext = field(default_factory=CallContext)
    house: CostMeter = field(default_factory=lambda: CostMeter(budget=0.5))   # housekeeping: memory writer, compaction
    approvals: "asyncio.Queue[tuple[str, str]]" = field(default_factory=asyncio.Queue)
    team_requests: "asyncio.Queue[int]" = field(default_factory=asyncio.Queue)
    permissions: dict[str, asyncio.Future] = field(default_factory=dict)
    approval_version: str = ""
    awaiting_approval: bool = False
    plan_steps: list[Any] = field(default_factory=list)
    plan_meta: dict = field(default_factory=dict)
    evidence: str = ""
    team_cache: dict = field(default_factory=dict)
    started: float = field(default_factory=time.monotonic)
    tools: ToolRun | None = None        # shared by every tool call of this run (source numbers, allowed links)

    def __post_init__(self) -> None:
        # Housekeeping is work for this question and shares its hard spending cap.
        self.house = self.meter
        if self.tools is None:
            self.tools = ToolRun(chat_id=self.chat_id, ctx=self.ctx)
        self.tools.permission = self.request_permission

    def checkpoint(self) -> None:
        """Persist results before another step starts, including on Stop/disconnect."""
        from app import memory
        from dataclasses import asdict
        if self.plan_steps:
            self.view.setdefault("meta", {})["planResults"] = [asdict(s) for s in self.plan_steps]
        memory.update_message(self.req.get("id", self.run_id), content=self.view["text"], meta={"view": self.view}, cost=self.meter.usd,
                              model=self.view.get("meta", {}).get("model"))

    def partial_text(self, reason: str) -> str:
        completed = [f"## Step {i + 1}: {s.task}\n{s.result}" for i, s in enumerate(self.plan_steps) if s.result]
        left = [f"- {i + 1}. {s.task}" for i, s in enumerate(self.plan_steps) if s.status != "done"]
        if completed:
            return "\n\n".join([f"Partial result: {reason}", *completed, "Steps left:\n" + "\n".join(left)]).strip()
        agents = self.view.get("meta", {}).get("agentResults", {})
        if agents:
            return "\n\n".join([f"Partial result: {reason}", *(f"## {role}\n{answer}" for role, answer in agents.items())])
        return self.view["text"] or f"Stopped: {reason}. No answer was finished."

    def begin_approval(self) -> str:
        while not self.approvals.empty():
            self.approvals.get_nowait()
        self.approval_version = uuid.uuid4().hex
        self.awaiting_approval = True
        return self.approval_version

    async def request_permission(self, name: str, args: dict) -> bool:
        from app.core.privacy import redact
        pid = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.permissions[pid] = future
        await self.emit({"type": "permission", "id": pid, "tool": name, "description": f"Allow {name} for this action?",
                         "arguments": redact(json.dumps(args, ensure_ascii=False))})
        try:
            return bool(await asyncio.wait_for(future, max(0.1, self.remaining_time())))
        finally:
            self.permissions.pop(pid, None)
            await self.emit({"type": "permission", "id": pid, "tool": name, "description": "Permission request finished", "resolved": True})

    async def emit(self, event: dict[str, Any]) -> None:
        apply_event(self.view, event)
        if event["type"] in {"plan", "permission", "output", "agents", "call_usage", "model_thinking"}:
            self.checkpoint()
        await self.queue.put(event)

    async def status(self, text: str) -> None:
        await self.emit({"type": "status", "text": text})

    async def text(self, delta: str, replace: bool = False) -> None:
        if delta or replace:
            await self.emit({"type": "text", "delta": delta, "replace": replace})

    async def warn(self, message: str) -> None:
        await self.emit({"type": "warning", "message": message})

    async def cost(self) -> None:
        await self.emit({"type": "cost", "calls": self.meter.calls, "usd": round(self.meter.usd, 6)})

    def remaining_time(self) -> float:
        return self.deadline - time.monotonic()
