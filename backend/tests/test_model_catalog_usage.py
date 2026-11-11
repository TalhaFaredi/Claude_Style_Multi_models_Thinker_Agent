"""Catalog completeness and user-visible usage are separate from paid provider gates."""
from __future__ import annotations

import importlib

import pytest

from app.core.costmeter import CostMeter
from app.llm import CallContext, ChatResult, ModelInfo, Usage, registry


def test_catalog_keeps_unpriced_and_nonchat_models_with_honest_cost_bands():
    registry._build([
        {"id": "vendor/text", "name": "Text", "context_length": 100_000,
         "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
         "pricing": {"prompt": "0.000001", "completion": "0.000003", "request": "0.0002"}},
        {"id": "vendor/unpriced", "context_length": 32_000,
         "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}, "pricing": {}},
        {"id": "vendor/image-output", "context_length": 32_000,
         "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]},
         "pricing": {"prompt": "0.000001", "completion": "0.000003"}},
        {"id": "vendor/responses-only", "context_length": 32_000,
         "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
         "endpoints": ["/api/v1/responses"],
         "pricing": {"prompt": "0.000001", "completion": "0.000003"}},
    ])
    ids = {item.id for item in registry.list(provider="openrouter")}
    assert {"vendor/text", "vendor/unpriced", "vendor/image-output", "vendor/responses-only"} <= ids
    priced = registry.get("vendor/text").to_api()
    assert priced["tentativeCosts"]["small"]["minUsd"] == pytest.approx(.0018)
    assert priced["tentativeCosts"]["small"]["maxUsd"] == pytest.approx(.0082)
    assert priced["tentativeCosts"]["high"]["maxTokens"] == 100_000
    assert not priced["tentativeCosts"]["high"]["fits"]
    unpriced = registry.get("vendor/unpriced").to_api()
    assert unpriced["priceKnown"] is False and unpriced["callCost"] is None
    assert unpriced["tentativeCosts"]["small"]["minUsd"] is None
    nonchat = registry.get("vendor/image-output").to_api()
    assert nonchat["chatCompatible"] is False and nonchat["available"] is False
    assert "chat-completions" in nonchat["whyUnavailable"]
    assert registry.get("vendor/responses-only").available is False


def test_conditional_long_context_prices_affect_tentative_and_reserved_costs():
    model = ModelInfo("vendor/long", "Long", "Vendor", "openrouter", True, False, False,
                      600_000, 1.0, 3.0, price_overrides=[
                          {"min_prompt_tokens": 200_000, "prompt": "0.000002", "completion": "0.000004"},
                      ])
    assert model.quote_rates(200_000) == (1.0, 3.0)
    assert model.quote_rates(200_001) == (2.0, 4.0)
    high = model.tentative_costs()["high"]
    assert high["fits"] and high["maxUsd"] == pytest.approx(1.3)
    assert model.call_cost(350_000, 150_000) == pytest.approx(1.3)


async def test_each_real_call_reports_usage_and_only_returned_thinking(monkeypatch):
    client = importlib.import_module("app.llm.client")
    info = ModelInfo("vendor/test", "Test", "Vendor", "openrouter", True, False, True,
                     100_000, 1.0, 2.0, price_known=True)
    registry.models[info.id] = info
    events = []

    async def fake_call(*args):
        return ChatResult(text="Answer", reasoning="Returned summary. Second point.", model=info.id,
                          usage=Usage(prompt=100, completion=20, reasoning=5, cost=.00014))

    monkeypatch.setattr(client, "_call_once", fake_call)
    ctx = CallContext(meter=CostMeter(1), chat_id="c1", run_id="r1", label="Critic", on_event=events.append)
    result = await client.complete(info.id, [{"role": "user", "content": "Question"}], stage="agent:round1",
                                   ctx=ctx, max_tokens=100, thinking="low", allow_fallback=False)
    assert result.text == "Answer"
    usage, thought = events
    assert usage == {"type": "call_usage", "stage": "agent:round1", "model": info.id,
                     "provider": "openrouter", "label": "Critic", "inTokens": 100, "outTokens": 20,
                     "reasoningTokens": 5, "usd": .00014, "estimated": False, "ok": True}
    assert thought["type"] == "model_thinking" and thought["available"]
    assert thought["label"] == "Critic" and thought["notes"] == ["Returned summary.", "Second point."]


def test_reasoning_details_use_exposed_text_and_ignore_encrypted_payload():
    client = importlib.import_module("app.llm.client")
    assert client._returned_reasoning({"reasoning_details": [
        {"type": "reasoning.summary", "summary": "Provider summary."},
        {"type": "reasoning.encrypted", "data": "secret ciphertext"},
    ]}) == "Provider summary."
    assert client._returned_reasoning({"reasoning_details": [{"type": "reasoning.encrypted", "data": "cipher"}]}) == ""


async def test_a_call_that_never_asked_for_thinking_adds_no_thinking_row(monkeypatch):
    client = importlib.import_module("app.llm.client")
    info = ModelInfo("vendor/plain", "Plain", "Vendor", "openrouter", True, False, True, 100_000, 1.0, 2.0, price_known=True)
    registry.models[info.id] = info
    events = []

    async def fake_call(*args):
        return ChatResult(text='{"pass": true}', model=info.id, usage=Usage(prompt=50, completion=5, cost=.00001))

    monkeypatch.setattr(client, "_call_once", fake_call)
    ctx = CallContext(meter=CostMeter(1), on_event=events.append)
    await client.complete(info.id, [{"role": "user", "content": "q"}], stage="checker", ctx=ctx, max_tokens=50, thinking="off", allow_fallback=False)
    assert [e["type"] for e in events] == ["call_usage"]
    await client.complete(info.id, [{"role": "user", "content": "q"}], stage="answer", ctx=ctx, max_tokens=50, thinking="low", allow_fallback=False)
    assert events[-1]["type"] == "model_thinking" and events[-1]["available"] is False   # asked, nothing returned: say so
