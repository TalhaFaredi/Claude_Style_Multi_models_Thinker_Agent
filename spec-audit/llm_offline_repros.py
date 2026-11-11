"""Audit-only deterministic provider mocks. Never contacts a provider or the real database."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATA_DIR"] = str(ROOT / "spec-audit" / "runtime-llm-audit")
sys.path.insert(0, str(ROOT / "backend"))

import httpx

from app.core import db
from app.core.costmeter import CostMeter
import importlib

client = importlib.import_module("app.llm.client")
from app.llm.registry import ModelInfo, registry
from app import llm, tools
from app.pipeline.runtime import RunContext, fresh_view
from app.modes.common.tool_loop import tool_loop
from app.tools.base import Tool, ToolResult


async def main():
    db.reset_for_tests()
    info = ModelInfo("audit/model", "Audit", "Audit", "openrouter", True, False, True, 100000, 0, 1000)
    registry.models = {info.id: info}
    original_once = client._call_once

    async def delayed_success(model, body, *args):
        await asyncio.sleep(0.01)
        return client.ChatResult(text="ok", model=model.id, usage=client.Usage(completion=body["max_tokens"], cost=model.call_cost(0, body["max_tokens"])))

    client._call_once = delayed_success
    meter = CostMeter(0.1)
    await asyncio.gather(*(client.complete(info.id, [], stage="audit", ctx=client.CallContext(meter=meter), max_tokens=100, allow_fallback=False) for _ in range(2)))
    print(json.dumps({"case": "parallel_budget", "budget": meter.budget, "spent": meter.usd, "calls": meter.calls}))

    meter = CostMeter(0.1)
    await client.complete(info.id, [], stage="audit", ctx=client.CallContext(meter=meter), max_tokens=100, thinking="high", allow_fallback=False)
    print(json.dumps({"case": "reasoning_budget", "budget": meter.budget, "spent": meter.usd, "requested_visible_tokens": 100, "provider_max_tokens": 4196}))

    attempt = 0
    streamed = []

    async def partial_then_retry(model, body, stream, on_text, on_reasoning):
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            await client._maybe(on_text("PARTIAL BAD DRAFT. "))
            raise client.LLMError("mock disconnect", retriable=True)
        await client._maybe(on_text("Correct answer."))
        return client.ChatResult(text="Correct answer.", model=model.id, usage=client.Usage(cost=0.01))

    client._call_once = partial_then_retry
    res = await client.complete(info.id, [], stage="audit", max_tokens=100, stream=True, on_text=streamed.append, allow_fallback=False)
    print(json.dumps({"case": "retry_stream", "returned_text": res.text, "visible_text": "".join(streamed), "attempts": attempt}))

    fallback = ModelInfo("nim:audit/fallback", "Audit fallback", "Audit", "nvidia", True, False, False, 100000, 0, 0)
    registry.models[fallback.id] = fallback
    tried = []

    async def rejected_key(model, *args):
        tried.append(model.id)
        if model.id == info.id:
            client._raise_for(401, "{}")
        return client.ChatResult(text="fallback works", model=model.id)

    client._call_once = rejected_key
    try:
        await client.complete(info.id, [], stage="audit", max_tokens=100)
    except client.LLMError:
        pass
    print(json.dumps({"case": "provider_credentials_fallback", "available_fallback": fallback.id, "actually_tried": tried}))
    client._call_once = original_once

    async def mock_response(request):
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n', headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_response)) as mock_http:
        client.client = lambda: mock_http
        client._endpoint = lambda model: ("https://audit.invalid", {})
        res = await client._read_stream(info, {}, None, None)
    print(json.dumps({"case": "truncated_stream", "text": res.text, "finish": res.finish, "logged_cost": res.usage.cost, "prompt_tokens": res.usage.prompt, "completion_tokens": res.usage.completion}))

    web_calls = []

    async def fake_web(args, state):
        web_calls.append(args)
        return ToolResult("mock web result")

    old_tool = tools.TOOLS["web_search"]
    tools.TOOLS["web_search"] = Tool("web_search", "web", "mock", {}, fake_web, lambda args: "mock web")
    loop_calls = 0

    async def scripted_model(model, messages, **kwargs):
        nonlocal loop_calls
        loop_calls += 1
        if loop_calls == 1:
            return client.ChatResult(tool_calls=[{"id": "1", "name": "web_search", "arguments": '{"query":"private text"}'}], model=info.id)
        return client.ChatResult(text="finished", model=info.id)

    llm.complete = scripted_model
    meter = CostMeter(1)
    rc = RunContext("run", "chat", {}, meter, {}, asyncio.Queue(), fresh_view("simple", "", {}, False), 10**20)
    await tool_loop(rc, info.id, [], [], stream_text=False)
    print(json.dumps({"case": "disabled_tool", "advertised_tool_names": [], "executed_web_calls": web_calls}))
    tools.TOOLS["web_search"] = old_tool

    from app.pipeline import engine
    from app.modes.common import Result

    async def fake_pipeline(rc, text, model):
        rc.meter.add("answer", 0.01, 10, 10)
        return Result("answer")

    async def fake_context(rc, model):
        return {"percent": 0}

    async def fake_memory_writer(chat, user, answer, ctx):
        ctx.meter.add("memory", 0.02, 10, 10)

    engine.pipeline = fake_pipeline
    engine.context_event = fake_context
    engine.memory.write_turn_memory = fake_memory_writer
    rc = RunContext("b" * 32, "a" * 32, {"id": "b" * 32, "prompt": "question", "simple": {"model": info.id}},
                    CostMeter(1), {"autoCompact": True}, asyncio.Queue(), fresh_view("simple", "", {}, False), 10**20)
    await engine.execute(rc)
    await asyncio.sleep(0.01)
    saved = db.one("SELECT cost FROM messages WHERE id=?", (rc.run_id,))["cost"]
    print(json.dumps({"case": "housekeeping_cost", "displayed_cost": rc.view["costUsd"], "saved_message_cost": saved,
                      "actual_meter_total_after_memory": rc.meter.usd + rc.house.usd}))


if __name__ == "__main__":
    asyncio.run(main())
