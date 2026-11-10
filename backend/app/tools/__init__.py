"""Tools Hub (spec Part 1 section 3 and Mode A): code the model can ask to run.

    tool            setting   what it does                                   safety
    web_search      web       top web results with numbered sources          read-only
    read_webpage    web       main text of one page from those results       allow-list + public IPs only
    calculator      code      exact arithmetic                               parses math only, never runs code
    search_files    files     passages from this chat's files                this chat only
    run_code        code      Python in a Docker sandbox                     permission + live environment check

Rules from the spec:
  * the tool list sent to the model holds only the tools this question needs (`specs_for`)
  * models without tool support get no tools (C9); the caller says so
  * at most 10 tool calls per answer (C10, enforced in app/modes/common/tool_loop.py)
  * a risky tool asks the user first (C11); unavailable tools are never offered
To add a tool: write a module with a `TOOL = Tool(...)`, then add it to TOOLS below.
"""
from __future__ import annotations

import time
import asyncio
from dataclasses import replace

from app.core import db

from app.tools import calculator, code_runner, file_search, read_webpage, web_search
from app.tools.base import Tool, ToolResult, ToolRun

TOOLS: dict[str, Tool] = {t.name: t for t in (web_search.TOOL, read_webpage.TOOL, calculator.TOOL, file_search.TOOL, code_runner.TOOL)}


def specs_for(settings: set[str], *, model_has_tools: bool, include_files: bool = False) -> list[dict]:
    """Offer enabled, available tools. Risky actions still require permission at execution time."""
    if not model_has_tools:
        return []
    out = []
    for t in TOOLS.values():
        if t.setting not in settings or not t.available:
            continue
        if t.name == "search_files" and not include_files:
            continue
        out.append(t.spec())
    return out


def running_label(name: str, args: dict) -> str:
    t = TOOLS.get(name)
    return t.running_label(args) if t else f"Running {name}..."


async def execute(name: str, args: dict, state: ToolRun, *, allowed: set[str] | None = None) -> ToolResult:
    started = time.monotonic()
    result = ToolResult("The tool was not permitted.", ok=False, done_label="Tool refused")
    reason = "refused"
    try:
        permitted = state.allowed_tools if allowed is None else allowed
        if name not in permitted:
            reason = "not in this answer's enabled allow-list"
            return result
        if state.calls >= state.max_calls:
            reason = "tool call limit reached"
            result = ToolResult("Tool call limit reached. Answer using the results already gathered.", ok=False, done_label="Tool limit reached")
            return result
        state.calls += 1  # no await between checking and booking: safe for concurrent async calls
        t = TOOLS.get(name)
        if t is None or not t.available:
            reason = "unknown or unavailable"
            result = ToolResult(f"The tool {name} is not available.", ok=False, done_label=f"{name} unavailable")
            return result
        if not _valid_arguments(t, args):
            reason = "invalid arguments"
            result = ToolResult("Tool arguments do not match the required schema.", ok=False, done_label="Invalid tool arguments")
            return result
        if t.risky and (state.permission is None or not await state.permission(name, args)):
            reason = "permission denied"
            result = ToolResult("The user did not allow this action. Continue without it.", ok=False, done_label="Permission denied")
            return result
        result = await t.run(args, state)
        reason = "tool reported failure" if not result.ok else ""
        return result
    except asyncio.CancelledError:
        reason = "cancelled"
        raise
    except Exception as e:   # a broken tool must not break the answer: tell the model and move on
        reason = type(e).__name__
        result = ToolResult(f"The tool failed ({type(e).__name__}). Continue without it.", ok=False, done_label=f"{name} failed")
        return result
    finally:
        db.run("INSERT INTO tool_calls(ts,run_id,chat_id,scope_id,tool,ms,ok,error) VALUES(?,?,?,?,?,?,?,?)",
               (db.now(), state.ctx.run_id if state.ctx else None, state.chat_id, state.scope_id, name[:100],
                round((time.monotonic() - started) * 1000), int(result.ok), reason or None))


def _valid_arguments(tool: Tool, args) -> bool:
    if not isinstance(args, dict):
        return False
    props = tool.parameters.get("properties", {})
    if any(key not in args for key in tool.parameters.get("required", [])) or any(key not in props for key in args):
        return False
    types = {"string": str, "object": dict, "array": list, "boolean": bool, "integer": int, "number": (int, float)}
    for key, value in args.items():
        schema = props[key]
        kind = schema.get("type")
        if kind in types and (not isinstance(value, types[kind]) or (isinstance(value, bool) and kind in ("integer", "number"))):
            return False
        if "enum" in schema and value not in schema["enum"]:
            return False
        if isinstance(value, str) and len(value) > min(schema.get("maxLength", 100000), 100000):
            return False
    return True


async def refresh_availability() -> list[dict]:
    ok, reason = await code_runner.health()
    TOOLS["run_code"] = replace(code_runner.TOOL, available=ok, why_unavailable=reason)
    return availability()


def availability() -> list[dict]:
    """For GET /api/config: what the Setup dialog can show for each tool."""
    return [{"name": t.name, "setting": t.setting, "available": t.available, "risky": t.risky, "reason": t.why_unavailable} for t in TOOLS.values()]


__all__ = ["TOOLS", "Tool", "ToolResult", "ToolRun", "specs_for", "running_label", "execute", "availability", "refresh_availability"]
