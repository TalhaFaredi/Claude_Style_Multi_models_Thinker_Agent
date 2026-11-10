"""The plan: steps, validation and how each step runs (spec section 6 and team rules T1 to T3).

Each step stores its task, done-test, easy / hard / tool, tools, needs (steps that must finish first) and
status. The model's plan is never trusted as-is: normalize() enforces the 20-step limit, only-earlier
dependencies (so there can be no cycle), known tools and kinds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app import files, llm, prompts, skills
from app.core.config import LIMITS
from app.pipeline.runtime import RunContext

TOOL_NAMES = {"web_search": "web search", "search_files": "file search", "build_output": "output builder"}
FORMAT_RE = re.compile(r"pdf|png|md|html|txt|text|code:[a-z0-9]{1,5}")


@dataclass
class Step:
    task: str
    done_test: str
    kind: str                       # easy | hard | tool
    tools: list[str] = field(default_factory=list)
    needs: list[int] = field(default_factory=list)
    status: str = "waiting"         # planned | waiting | running | checking | retry | done | failed
    note: str = ""
    tone: str = "hint"
    result: str = ""
    retries: int = 0
    use_team: bool = False
    artifact: dict | None = None


def normalize(data: dict | None, offset: int = 0) -> tuple[list[Step], dict]:
    """Validate the model's plan. `offset` = number of steps already done (re-plans number on from there)."""
    meta = {"title": "Plan", "final_format": "text"}
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        return [], meta
    meta["title"] = str(data.get("title") or "Plan")[:80]
    ff = str(data.get("final_format") or "text").lower()
    meta["final_format"] = ff if FORMAT_RE.fullmatch(ff) else "text"
    steps: list[Step] = []
    for raw in data["steps"][:max(0, LIMITS.max_plan_steps - offset)]:
        if not isinstance(raw, dict) or not str(raw.get("task") or "").strip():
            continue
        i = len(steps) + offset
        needs = sorted({n for n in (raw.get("needs") or []) if isinstance(n, int) and 0 <= n < i})
        kind = raw.get("kind") if raw.get("kind") in ("easy", "hard", "tool") else "easy"
        tl = [t for t in (raw.get("tools") or []) if t in TOOL_NAMES]
        if kind == "tool" and "build_output" in tl:
            needs = list(range(i))  # a final file must wait for all preceding content
        steps.append(Step(str(raw["task"]).strip()[:200], str(raw.get("done_test") or "The step's result answers the task.")[:200], kind, tl, needs))
    return steps, meta


def step_mode(step: Step, run_in: str) -> str:
    """T1: Simple -> every step alone. T2: Auto -> hard steps use the team. Thinker -> every thinking step
    uses the team. T3: a step that only runs a tool always runs alone (a team adds cost, not quality)."""
    if step.kind == "tool":
        return "simple"
    if step.use_team:
        return "team"
    if run_in == "simple":
        return "simple"
    if run_in == "thinker":
        return "team"
    return "team" if step.kind == "hard" else "simple"


def mode_label(step: Step, run_in: str, team_line: str) -> str:
    tl = ", ".join(TOOL_NAMES[t] for t in step.tools if t in TOOL_NAMES)
    if step_mode(step, run_in) == "team":
        return f"Thinker: {team_line}" + (f" + {tl}" if tl else "")
    return "Simple" + (f" + {tl}" if tl else "")


async def make_plan(rc: RunContext, goal: str, *, note: str = "", done: list[Step] | None = None, failed: str = "") -> tuple[list[Step], dict]:
    """Write (or re-write) the plan. A strong model can write the plan while cheap models run the easy steps."""
    model = rc.req.get("planModel") or rc.req["simple"]["model"]
    lines = []
    if files.chat_readings(rc.chat_id):
        lines.append("The user attached files; a step may use search_files.")
    if done:
        lines.append("Steps already DONE (numbered; do not repeat them): " + "; ".join(f"{i}: {s.task}" for i, s in enumerate(done))
                     + f". Write ONLY the remaining steps; the first new step has index {len(done)}, and needs may point to done steps.")
    lines.append(f"At most {max(0, LIMITS.max_plan_steps - len(done or []))} remaining steps. Keep the original goal and all user constraints.")
    if failed:
        lines.append(f"A step failed: {failed}. Plan a different way to reach the goal.")
    if note:
        lines.append(f"The user asked for this change to the plan: {note}")
    system = prompts.render("planner/plan_writer") + "\n\n" + skills.render([s for s in [skills.get("writing-plans")] if s])
    for _ in range(2):
        data, _res = await llm.ask_json(model, system, f"Goal: {goal}\n" + "\n".join(lines), stage="plan", ctx=rc.ctx, max_tokens=1100, temperature=0.2)
        steps, meta = normalize(data, offset=len(done or []))
        if steps:
            return steps, meta
    # the model could not produce a plan: one honest step is better than failing the run
    return ([Step(goal[:200], "The answer fully addresses the goal.", "easy")] if len(done or []) < LIMITS.max_plan_steps else []), {"title": "Answer", "final_format": "text"}


def plan_view(steps: list[Step], run_in: str, team_line: str) -> list[dict]:
    """The plan card's rows."""
    return [{"task": s.task, "doneTest": s.done_test, "kind": s.kind, "modeLabel": mode_label(s, run_in, team_line), "status": s.status,
             "note": s.note or None, "noteTone": s.tone if s.note else None,
             "canUseTeam": s.status == "failed" and s.kind != "tool" and run_in == "simple" and not s.use_team} for s in steps]
