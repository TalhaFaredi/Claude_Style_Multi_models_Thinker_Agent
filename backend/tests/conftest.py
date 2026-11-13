"""Offline test setup: a fresh in-memory database and a scripted fake LLM. No network, no credits."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

# Tests write uploaded files and generated outputs here, never into the real backend/data folder.
# Set before `app` is imported, because folder paths are read once at import time.
os.environ["DATA_DIR"] = str(Path(__file__).resolve().parents[1] / "data_test")
# The existing suite exercises the single-user core; tests/test_accounts.py switches accounts on explicitly.
os.environ["AUTH_REQUIRED"] = "0"

import pytest  # noqa: E402

from app import llm  # noqa: E402
from app.core import db  # noqa: E402
from app.llm import ChatResult, Usage, registry  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    from app.pipeline.engine import manager
    manager.runs.clear()
    db.reset_for_tests()
    db.set_setting("embeddings", False)   # meaning search would call the network; keyword search covers the tests
    registry._build([])                   # featured models only, no network
    # The offline fixture supplies deterministic mock prices. Production never guesses unknown prices.
    for info in registry.models.values():
        if info.provider == "openrouter":
            info.price_known = True
    registry.provider_status = {"openrouter": {"ok": True, "reason": ""}, "nvidia": {"ok": False, "reason": "403"}}
    registry._apply_status()
    yield


class FakeLLM:
    """Replaces llm.complete. `on(stage, reply)` maps a stage (or '*') to a str, a dict/list (sent as JSON) or a callable."""

    def __init__(self):
        self.calls: list[dict] = []
        self.replies: dict[str, object] = {}

    def on(self, stage: str, reply):
        self.replies[stage] = reply
        return self

    async def __call__(self, model, messages, *, stage, ctx=None, **kw):
        reply = self.replies.get(stage, self.replies.get("*", "ok"))
        text = reply(messages) if callable(reply) else (json.dumps(reply) if isinstance(reply, (dict, list)) else str(reply))
        self.calls.append({"model": model, "stage": stage, "messages": messages, "kw": kw})
        if kw.get("stream") and kw.get("on_text"):
            r = kw["on_text"](text)
            if asyncio.iscoroutine(r):
                await r
        usage = Usage(prompt=100, completion=20, cost=0.0001)
        if ctx and ctx.meter:
            ctx.meter.add(stage, usage.cost, usage.prompt, usage.completion)
        return ChatResult(text=text, usage=usage, model=model)


@pytest.fixture
def fake_llm(monkeypatch):
    """Every module calls models as `llm.complete` / `llm.ask_json`, so one patch covers the whole app."""
    f = FakeLLM()
    monkeypatch.setattr(llm, "complete", f)
    return f
