"""The tool loop (Mode A, Figure 2): call the model; if it asks for a tool, run it, add the result, and call
again, until it answers without a tool. At most 10 tool calls per answer (C10); after that the model is
told to answer with what it has."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from app import llm, tools
from app.core.config import LIMITS
from app.pipeline.runtime import RunContext, notes_from_reasoning
from app.modes.common.streaming import DEFAULT_MAX_TOKENS


@dataclass
class LoopResult:
    text: str = ""
    citations: list[str] = field(default_factory=list)
    tool_calls: int = 0
    finish: str = ""
    model: str = ""
    first_usage: llm.Usage | None = None


def _assistant_turn(res: llm.ChatResult) -> dict:
    return {"role": "assistant", "content": res.text or None,
            "tool_calls": [{"id": tc["id"] or f"call_{i}", "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"] or "{}"}}
                           for i, tc in enumerate(res.tool_calls)]}


async def tool_loop(rc: RunContext, model_id: str, messages: list[dict], tool_specs: list[dict], *, thinking: str = "off", temperature: float = 0.7,
                    max_tokens: int = DEFAULT_MAX_TOKENS, stage: str = "answer", stream_text: bool = True, show_tools: bool = True,
                    exclude: set[str] | None = None) -> LoopResult:
    msgs = list(messages)
    out = LoopResult()
    reasoning = ""
    t0 = time.monotonic()

    async def on_reason(delta: str):
        nonlocal reasoning
        if not reasoning:
            await rc.status("Thinking")
        reasoning += delta

    offered = {s["function"]["name"] for s in tool_specs}
    for _turn in range(LIMITS.max_tool_calls + 1):
        allow = tool_specs if rc.tools.calls < rc.tools.max_calls else None
        res = await llm.complete(model_id, msgs, stage=stage, ctx=rc.ctx, tools=allow, thinking=thinking, temperature=temperature,
                                 max_tokens=max_tokens, stream=True, on_text=rc.text if stream_text else None, on_reasoning=on_reason, exclude=exclude,
                                 on_reset=(lambda: rc.text("", replace=True)) if stream_text else None)
        out.model, out.finish = res.model, res.finish
        out.first_usage = out.first_usage or res.usage
        await rc.cost()
        if not res.tool_calls:
            out.text = res.text
            break
        if not allow:
            out.text = res.text or "The tool call limit was reached. I can continue with the results already gathered in a new request."
            break
        msgs.append(_assistant_turn(res))
        for i, tc in enumerate(res.tool_calls):
            call_id = tc["id"] or f"call_{i}"
            if rc.tools.calls >= rc.tools.max_calls:
                msgs.append({"role": "tool", "tool_call_id": call_id, "content": "Tool call limit reached. Answer with what you already have."})
                continue
            try:
                args = json.loads(tc["arguments"] or "{}")
            except ValueError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            if show_tools:
                await rc.emit({"type": "tool", "state": "running", "label": tools.running_label(tc["name"], args)})
            r = await tools.execute(tc["name"], args, rc.tools, allowed=offered)
            out.tool_calls += 1
            out.citations += [c for c in r.citations if c not in out.citations]
            if show_tools:
                await rc.emit({"type": "tool", "state": "done", "label": r.done_label or "Tool finished"})
            msgs.append({"role": "tool", "tool_call_id": call_id, "content": r.text})
        await rc.status("Writing")
    else:
        out.text = "The tool loop limit was reached. The results already gathered have been kept."

    if reasoning and stage in ("answer", "compose"):
        await rc.emit({"type": "thinking", "notes": notes_from_reasoning(reasoning), "seconds": max(1, round(time.monotonic() - t0))})
    return out
