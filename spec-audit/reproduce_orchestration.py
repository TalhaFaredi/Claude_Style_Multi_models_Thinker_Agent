"""Offline audit reproductions. Assertions describe observed defects, not desired behavior.

Run from repository root: backend/.venv/Scripts/python.exe spec-audit/reproduce_orchestration.py
No external requests; database is in memory; provider calls are mocked.
"""
import asyncio
import importlib
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATA_DIR"] = str(ROOT / "spec-audit" / "runtime")
sys.path.insert(0, str(ROOT / "backend"))

from app import llm, memory
from app.core import db
from app.core.costmeter import CostMeter
from app.llm import ChatResult, Usage, registry
from app.modes.planner.plan import Step, normalize
from app.pipeline import checker
from app.pipeline.engine import manager
from tests.conftest import FakeLLM

planner = importlib.import_module("app.modes.planner.run")
steps_module = importlib.import_module("app.modes.planner.steps")
assemble_module = importlib.import_module("app.modes.planner.assemble")
thinker_module = importlib.import_module("app.modes.thinker.run")


def reset():
    db.reset_for_tests()
    db.set_setting("embeddings", False)
    db.set_setting("longMemory", False)
    registry._build([])


def req(**overrides):
    result = {
        "id": "audit-run", "chatId": "audit-chat", "mode": "planner",
        "prompt": "Prepare a two-step answer", "files": [],
        "simple": {"model": "qwen/qwen3.7-flash", "thinking": "off", "style": "balanced", "tools": {}},
        "team": {"source": "same", "model": "meta-llama/llama-3.1-8b-instruct", "agents": 3,
                 "mixed": [], "style": "independent", "rounds": 2, "composer": "auto"},
        "runIn": "auto", "budgetUsd": 1.0, "allowOver": False, "retryOf": None,
    }
    result.update(overrides)
    return result


async def main():
    reset()
    rc = SimpleNamespace(req=req(), approvals=asyncio.Queue(), status=AsyncMock())
    for i in range(6):
        await rc.approvals.put(("edit", f"edit {i}"))
    make = AsyncMock(return_value=([Step("Replacement", "done", "easy")], {}))
    with patch.object(planner, "make_plan", make), patch.object(planner, "emit_plan", AsyncMock()):
        await asyncio.wait_for(planner._approve(rc, "goal", [Step("Original", "done", "easy")], {}), 1)
    assert make.await_count == 5
    print("REPRODUCED: sixth Edit exits initial approval gate without any Approve")

    rc = SimpleNamespace(req=req(), approvals=asyncio.Queue())
    await rc.approvals.put(("edit", "Do not execute; change the plan"))
    replacement = [Step(f"New task {i}", "done", "easy") for i in range(4)]
    make = AsyncMock(return_value=(replacement, {}))
    emit = AsyncMock()
    with patch.object(planner, "make_plan", make), patch.object(planner, "emit_plan", emit):
        result, _ = await planner._replan(rc, "goal", [Step("failed", "done", "easy", status="failed")], {}, 0)
    assert make.await_count == 1 and all(s.status == "waiting" for s in result)
    assert emit.await_args_list[-1].args[2] == "Running"
    print("REPRODUCED: Edit at substantial re-plan approval is ignored and execution resumes")

    replacement, _ = normalize({"steps": [{"task": str(i)} for i in range(20)]}, offset=19)
    assert len(replacement) + 19 == 39
    print("REPRODUCED: re-plan normalization permits 19 completed + 20 new = 39 plan steps")

    rc = SimpleNamespace(req=req(), ctx=None, cost=AsyncMock())
    alone = AsyncMock(return_value=("draft", []))
    team = AsyncMock()
    check = AsyncMock(side_effect=[checker.CheckResult(False, "wrong"), checker.CheckResult(True)])
    with patch.object(steps_module, "emit_plan", AsyncMock()), patch.object(steps_module, "_run_alone", alone), \
            patch.object(steps_module, "run_thinker", team), patch.object(checker, "check", check):
        assert await steps_module.run_step(rc, "goal", [Step("Easy task", "done", "easy")], 0, set())
    assert alone.await_count == 2 and team.await_count == 0
    print("REPRODUCED: failed Simple step in Auto retries in Simple instead of escalating to team")

    rc = SimpleNamespace(req=req(), ctx=None, cost=AsyncMock(), text=AsyncMock())
    complete = AsyncMock(return_value=ChatResult(text="UNCHECKED ASSEMBLY", usage=Usage(), model="test"))
    check = AsyncMock()
    with patch.object(llm, "complete", complete), patch.object(checker, "check", check):
        result = await assemble_module.assemble(rc, "goal", [Step("one", "done", "easy", result="checked step")], {"final_format": "text"}, set())
    assert result.text == "UNCHECKED ASSEMBLY" and check.await_count == 0
    print("REPRODUCED: Planner final assembly bypasses Checker")

    reset()
    started_second = asyncio.Event()
    fake = FakeLLM().on("plan", {"title": "T", "final_format": "text", "steps": [
        {"task": "First", "kind": "easy"}, {"task": "Second", "kind": "easy", "needs": [0]}]})
    fake.on("step", "FIRST_COMPLETED_RESULT_987").on("checker", {"pass": True})
    step_calls = 0

    async def complete(*args, stage="", **kwargs):
        nonlocal step_calls
        if stage == "step":
            step_calls += 1
            if step_calls == 2:
                started_second.set()
                await asyncio.Future()
        return await fake(*args, stage=stage, **kwargs)

    with patch.object(llm, "complete", complete):
        run = await manager.start(req())
        while True:
            event = await asyncio.wait_for(run.rc.queue.get(), 3)
            if event and event["type"] == "plan" and event["awaitingApproval"]:
                break
        await run.rc.approvals.put(("approve", ""))
        await asyncio.wait_for(started_second.wait(), 3)
        assert manager.stop(run.rc.run_id)
        await asyncio.wait_for(run.task, 3)
    saved = memory.ui_messages("audit-chat")[-1]
    assert saved["text"] == "" and "FIRST_COMPLETED_RESULT_987" not in str(saved)
    assert saved["plan"]["steps"][0]["status"] == "done"
    print("REPRODUCED: Stop after a completed Planner step saves its status but loses its actual result")

    reset()
    memory.add_message("chat-a", "assistant", "Original archived answer", mid="same-run-id")
    memory.add_message("chat-b", "assistant", "New answer", mid="same-run-id")
    assert memory.ui_messages("chat-a") == []
    print("REPRODUCED: reusing a run/message ID in another chat replaces the original archived message")

    async def broken_checker(*args, **kwargs):
        raise RuntimeError("checker unavailable")

    with patch.object(llm, "ask_json", broken_checker):
        result = await checker.check("question", "unverified answer", ctx=llm.CallContext())
    assert result.passed and not result.issues
    print("REPRODUCED: unavailable Checker silently treats unverified answer as passing")

    reset()
    rc = SimpleNamespace(req=req(), chat_id="audit-chat", ctx=None, tools=None, settings={"windowCap": 32000},
                         meter=CostMeter(1), status=AsyncMock(), warn=AsyncMock(), emit=AsyncMock(), text=AsyncMock())
    rc.req["team"].update(style="together", rounds=2)
    round_number = 0

    async def round_with_late_failure(rc, progress, agents, *args):
        nonlocal round_number
        round_number += 1
        for i, agent in enumerate(agents):
            agent.answer = agent.first = "A result"
            agent.alive = round_number == 1 or i == 0
        return 3 if round_number == 1 else 1

    compose = AsyncMock(return_value=("Merged one remaining answer", None))
    fallback = AsyncMock()
    built = SimpleNamespace(messages=[{"role": "system", "content": "rules"}, {"role": "user", "content": "q"}], tokens=100)
    with patch.object(thinker_module.memory, "build", AsyncMock(return_value=built)), \
            patch.object(thinker_module, "skills_note", AsyncMock()), \
            patch.object(thinker_module, "run_round", round_with_late_failure), \
            patch.object(thinker_module, "agree", AsyncMock(return_value=False)), \
            patch.object(thinker_module, "compose", compose), \
            patch.object(thinker_module, "run_simple", fallback), \
            patch.object(thinker_module, "stream_now", return_value=True):
        await thinker_module.run_thinker(rc, "Compare choices")
    assert compose.await_count == 1 and fallback.await_count == 0
    print("REPRODUCED: fewer than two agents survive round 2, but Thinker composes instead of Simple fallback")


if __name__ == "__main__":
    asyncio.run(main())
