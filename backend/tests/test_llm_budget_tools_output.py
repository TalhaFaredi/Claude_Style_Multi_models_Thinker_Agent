"""Regression tests for real budget/stream/tool boundaries, using transport mocks only."""
from __future__ import annotations

import asyncio
import importlib
import io
import uuid
from dataclasses import replace

import httpx
import pytest
from tenacity import wait_none

from app import tools
from app.core import db, usage
from app.core.config import DATA_DIR
from app.core.costmeter import BudgetExceeded, CostMeter
from app.llm import CallContext, ChatResult, LLMError, Usage
from app.llm.registry import ModelInfo, registry
from app.output import artifacts
from app.tools.base import Tool, ToolResult, ToolRun
from app.tools import code_runner

client = importlib.import_module("app.llm.client")


@pytest.fixture
def output_dir():
    # Use the explicitly isolated test data root; Windows profile temp folders can be inaccessible.
    folder = DATA_DIR / "output-tests" / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def model(mid="audit/model", provider="openrouter", *, pin=0, pout=1000, thinking=True):
    info = ModelInfo(mid, mid, "Audit", provider, True, False, thinking, 100000, pin, pout, featured=True)
    registry.models = {**registry.models, mid: info}
    return info


async def test_concurrent_requests_reserve_before_dispatch(monkeypatch):
    info, meter, dispatched = model(), CostMeter(0.1), []

    async def request(info, body, *args):
        dispatched.append(info.id)
        await asyncio.sleep(0.01)
        return ChatResult(text="ok", usage=Usage(completion=100, cost=0.1))

    monkeypatch.setattr(client, "_call_once", request)
    results = await asyncio.gather(*(client.complete(info.id, [], stage="test", ctx=CallContext(meter=meter), max_tokens=100,
                                                    allow_fallback=False) for _ in range(2)), return_exceptions=True)
    assert sum(isinstance(result, BudgetExceeded) for result in results) == 1
    assert len(dispatched) == 1 and meter.usd == pytest.approx(0.1) and meter.reserved == 0


async def test_reasoning_allowance_is_reserved_before_provider_call(monkeypatch):
    info, meter = model(), CostMeter(0.1)

    async def forbidden(*args):
        pytest.fail("The provider must not be called when reasoning would exceed the budget")

    monkeypatch.setattr(client, "_call_once", forbidden)
    with pytest.raises(BudgetExceeded):
        await client.complete(info.id, [], stage="test", ctx=CallContext(meter=meter), max_tokens=100, thinking="high", allow_fallback=False)
    assert meter.usd == meter.reserved == 0


def test_booking_reconciles_and_cannot_be_spent_twice():
    meter = CostMeter(1)
    booking = meter.reserve(0.8)
    with pytest.raises(BudgetExceeded):
        meter.reserve(0.3)
    booking.settle("answer", 0.4, 100, 20)
    with pytest.raises(RuntimeError):
        booking.settle("answer", 0.4, 100, 20)
    assert meter.remaining == pytest.approx(0.6)
    other = meter.reserve(0.6)
    other.release()
    other.release()
    assert meter.remaining == pytest.approx(0.6)


async def test_stream_retry_replaces_failed_attempt(monkeypatch):
    info, chunks, attempts, resets = model(pout=1), [], 0, []

    async def request(info, body, stream, on_text, on_reasoning):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            await client._maybe(on_text("abandoned "))
            raise LLMError("mock disconnect", retriable=True)
        await client._maybe(on_text("correct"))
        return ChatResult(text="correct", usage=Usage(cost=0.0001))

    def reset():
        resets.append(True)
        chunks.clear()

    monkeypatch.setattr(client, "_call_once", request)
    monkeypatch.setattr(client, "wait_exponential", lambda **kwargs: wait_none())
    result = await client.complete(info.id, [], stage="test", stream=True, max_tokens=100, allow_fallback=False,
                                   on_text=chunks.append, on_reset=reset)
    assert result.text == "correct" and "".join(chunks) == "correct" and len(resets) == 1


async def test_stream_without_reset_buffers_until_success(monkeypatch):
    info, chunks, attempts = model(pout=1), [], 0

    async def request(info, body, stream, on_text, on_reasoning):
        nonlocal attempts
        attempts += 1
        await client._maybe(on_text("bad" if attempts == 1 else "good"))
        if attempts == 1:
            raise LLMError("mock failure", retriable=True)
        return ChatResult(text="good")

    monkeypatch.setattr(client, "_call_once", request)
    monkeypatch.setattr(client, "wait_exponential", lambda **kwargs: wait_none())
    await client.complete(info.id, [], stage="test", stream=True, on_text=chunks.append, allow_fallback=False)
    assert chunks == ["good"]


async def test_truncated_stream_is_not_success_or_free(monkeypatch):
    info = model(pout=1)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'))
    async with httpx.AsyncClient(transport=transport) as http:
        monkeypatch.setattr(client, "client", lambda: http)
        monkeypatch.setattr(client, "_endpoint", lambda info: ("https://audit.invalid", {}))
        with pytest.raises(LLMError, match="completion marker") as exc:
            await client._read_stream(info, {"max_tokens": 100, "messages": []}, None, None)
    assert exc.value.usage.estimated and exc.value.usage.cost > 0


async def test_missing_usage_has_conservative_estimated_cost(monkeypatch):
    info = model(pout=1)
    data = 'data: {"choices":[{"delta":{"content":"answer"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=data))) as http:
        monkeypatch.setattr(client, "client", lambda: http)
        monkeypatch.setattr(client, "_endpoint", lambda info: ("https://audit.invalid", {}))
        result = await client._read_stream(info, {"max_tokens": 100, "messages": []}, None, None)
    assert result.usage.estimated and result.usage.cost > 0 and result.usage.completion == 100


async def test_cancelled_provider_request_is_accounted_and_logged(monkeypatch):
    info, meter, entered = model(pout=1), CostMeter(1), asyncio.Event()

    async def request(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(client, "_call_once", request)
    task = asyncio.create_task(client.complete(info.id, [], stage="test", ctx=CallContext(meter=meter), max_tokens=100, allow_fallback=False))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    row = db.one("SELECT * FROM calls WHERE model=?", (info.id,))
    assert row["usage_estimated"] == 1 and row["completed"] == 0 and row["cost"] > 0
    assert meter.reserved == 0 and meter.estimated_calls == 1
    assert usage.month_spent() == pytest.approx(row["cost"])


async def test_rejected_provider_key_uses_other_provider(monkeypatch):
    first, other, tried = model(pout=1), model("audit/fallback", "nvidia", pout=1), []
    registry.models = {first.id: first, other.id: other}

    async def request(info, *args):
        tried.append(info.id)
        if info.provider == "openrouter":
            client._raise_for(401, "{}")
        return ChatResult(text="fallback")

    monkeypatch.setattr(client, "_call_once", request)
    assert (await client.complete(first.id, [], stage="test")).text == "fallback"
    assert tried == [first.id, other.id]


async def test_disabled_tools_are_refused_and_traced():
    state = ToolRun("chat")
    result = await tools.execute("calculator", {"expression": "2+2"}, state, allowed=set())
    assert not result.ok and state.calls == 0
    assert db.one("SELECT error FROM tool_calls")["error"] == "not in this answer's enabled allow-list"


async def test_shared_scope_budget_survives_retries_and_children_keep_citations():
    state = ToolRun("chat", max_calls=2)
    assert (await tools.execute("calculator", {"expression": "2+2"}, state, allowed={"calculator"})).ok
    assert (await tools.execute("calculator", {"expression": "3+3"}, state, allowed={"calculator"})).ok
    assert not (await tools.execute("calculator", {"expression": "4+4"}, state, allowed={"calculator"})).ok
    child = state.child("step:2")
    assert child.calls == 0 and child.scope_id == "step:2"
    assert state.next_citation() == 1 and child.next_citation() == 2


async def test_risky_tool_permission_must_be_explicit(monkeypatch):
    executed = []

    async def action(args, state):
        executed.append(True)
        return ToolResult("ok")

    tool = Tool("audit_action", "code", "Action", {"type": "object", "properties": {}}, action, lambda args: "Action", risky=True)
    monkeypatch.setitem(tools.TOOLS, tool.name, tool)
    state = ToolRun("chat")
    assert not (await tools.execute(tool.name, {}, state, allowed={tool.name})).ok

    async def permit(name, args):
        return True

    state.permission = permit
    assert (await tools.execute(tool.name, {}, state, allowed={tool.name})).ok
    assert len(executed) == 1


def test_cache_specific_prices_and_ttl_are_used():
    info = model(pin=2, pout=0)
    info.price_cache_read, info.price_cache_write = 0.1, 2.5
    assert info.call_cost(1000, 0, cached=1000) == pytest.approx(0.0001)
    assert info.call_cost(1000, 0, cache_write=1000) == pytest.approx(0.0025)
    db.set_setting("promptCacheTtl", "1h")
    info.id = "anthropic/audit"
    messages = client._prepare_messages(info, [{"role": "system", "content": "rules"}])
    assert messages[0]["content"][0]["cache_control"]["ttl"] == "1h"


def test_png_deliverable_is_a_valid_raster(output_dir, monkeypatch):
    from PIL import Image
    monkeypatch.setattr(artifacts, "ARTIFACTS_DIR", output_dir)
    file = artifacts.build_artifact("chat", "Diagram", '{"width":512,"height":320,"elements":[{"type":"text","x":20,"y":20,"text":"Solar power"}]}', "png")
    saved = artifacts.get_artifact(file["id"])
    with Image.open(saved["path"]) as image:
        assert image.format == "PNG" and image.size == (512, 320)
    assert file["warning"] is None and file["format"] == "png"


def test_output_repairs_once_then_falls_back_honestly(output_dir, monkeypatch):
    monkeypatch.setattr(artifacts, "ARTIFACTS_DIR", output_dir)
    repaired = artifacts.build_artifact("chat", "Data", '{"a":1,}', "code:json")
    assert repaired["format"] == "code:json" and repaired["repaired"] and repaired["warning"] is None
    failed = artifacts.build_artifact("chat", "Code", "def broken(:", "code:py")
    assert failed["format"] == "txt" and failed["name"].endswith(".txt") and failed["warning"]


async def test_sandbox_availability_depends_on_daemon_and_image(monkeypatch):
    monkeypatch.setattr(code_runner, "docker_path", lambda: "docker")

    async def command(*args):
        return (0, "linux") if "info" in args else (1, "missing")

    monkeypatch.setattr(code_runner, "_command", command)
    ok, reason = await code_runner.health(force=True)
    assert not ok and "image" in reason.lower()
    cmd = code_runner.command("docker", "test-container")
    assert "--network=none" in cmd and "--read-only" in cmd and "--user=65534:65534" in cmd
    assert "--cap-drop=ALL" in cmd and "--pids-limit=32" in cmd and not any(arg in ("-v", "--volume", "--privileged") for arg in cmd)


async def test_web_fetch_connects_to_checked_ip_with_original_tls_hostname(monkeypatch):
    from app.tools import read_webpage
    captured = []

    async def addresses(host):
        return ["1.1.1.1"]

    def reply(request):
        captured.append(request)
        return httpx.Response(200, text="<main>Public document content</main>", headers={"content-type": "text/html"})

    constructor = httpx.AsyncClient
    monkeypatch.setattr(read_webpage, "public_addresses", addresses)
    monkeypatch.setattr(read_webpage.httpx, "AsyncClient", lambda **kwargs: constructor(transport=httpx.MockTransport(reply)))
    state = ToolRun("chat", allowed_urls={"https://example.org/doc": 1})
    assert (await read_webpage.fetch("https://example.org/doc", state)).ok
    assert captured[0].url.host == "1.1.1.1"
    assert captured[0].headers["host"] == "example.org"
    assert captured[0].extensions["sni_hostname"] == "example.org"


def test_acceptance_known_answers_are_strict_and_arithmetically_correct():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("acceptance", Path(__file__).with_name("live_spec_acceptance.py"))
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    assert acceptance.evaluate("FINAL: 66", "66")
    assert acceptance.evaluate(r"**FINAL:** \(\displaystyle \frac{5}{11}\)", "5/11")
    assert not acceptance.evaluate(r"**FINAL:** \(\frac{6}{11}\)", "5/11")
    assert not acceptance.evaluate("It might be 66 or 68", "66")
    assert not acceptance.evaluate("FINAL: 68", "66")
    assert sum(n for n in range(1, 101) if n % 2 and n % 3 and n % 5) == 1268
    solutions = [(a,b,c,d) for a in range(1,10) for b in range(1,10) for c in range(1,10) for d in range(1,10)
                 if len({a,b,c,d}) == 4 and a+b == 10 and c-d == 3 and a*c == 24 and b>d]
    assert solutions == [(3,7,8,5)]


async def test_mandatory_reasoning_retry_has_a_budgeted_minimum_allowance(monkeypatch):
    info = model("audit/requires-reasoning", pout=1)
    meter = CostMeter(.1)
    attempts = []
    async def request(info, body, *args):
        attempts.append((dict(body.get("reasoning", {})), body["max_tokens"]))
        if len(attempts) == 1:
            raise LLMError("reasoning is mandatory", status=400)
        return ChatResult(text="Correct answer", usage=Usage(completion=10, cost=.00001))
    monkeypatch.setattr(client, "_call_once", request)
    result = await client.complete(info.id, [], stage="test", ctx=CallContext(meter=meter), thinking="off", max_tokens=100, allow_fallback=False)
    assert result.text == "Correct answer"
    assert attempts == [({"enabled": False}, 100), ({"effort": "low"}, 1124)]
    assert meter.reserved == 0 and meter.usd == .00001
    assert client._body(info, [], stream=False, tools=None, temperature=None, max_tokens=100, thinking="off")["max_tokens"] == 1124
