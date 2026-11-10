"""Regression gates for approval, quality, stop, grounding and shared question budgets."""
import asyncio
import importlib
import json

import pytest
from fastapi import HTTPException

from app import llm, memory
from app.api import runs as runs_api
from app.api.schemas import ApprovalRequest, EditRequest, PermissionRequest
from app.core.costmeter import BudgetExceeded
from app.modes.common import Result
from app.pipeline import checker
from app.pipeline.engine import manager
from app.pipeline.runtime import RunContext, fresh_view
from app.core.costmeter import CostMeter
from types import SimpleNamespace
import time
from tests.test_pipeline import collect, req, text_of

planner = importlib.import_module("app.modes.planner.run")
thinker = importlib.import_module("app.modes.thinker.run")


async def waiting_plan(run):
    while True:
        event = await asyncio.wait_for(run.rc.queue.get(), 4)
        if event and event["type"] == "plan" and event["awaitingApproval"]:
            return event


def one_step(fake_llm):
    fake_llm.on("plan", {"title": "T", "final_format": "text", "steps": [{"task": "Do it", "kind": "easy"}]})
    fake_llm.on("step", "A checked step.").on("checker", {"pass": True}).on("plan:assemble", "A final checked deliverable.")


async def test_six_edits_never_approve_and_stale_approval_is_rejected(fake_llm):
    one_step(fake_llm)
    run = await manager.start(req(mode="planner"))
    first = await waiting_plan(run)
    version = first["version"]
    for i in range(6):
        await runs_api.edit_plan(run.rc.run_id, EditRequest(note=f"change {i}", planVersion=version))
        proposal = await waiting_plan(run)
        version = proposal["version"]
    assert not any(c["stage"] == "step" for c in fake_llm.calls)
    with pytest.raises(HTTPException) as stale:
        await runs_api.approve(run.rc.run_id, ApprovalRequest(planVersion=first["version"]))
    assert stale.value.status_code == 409
    await runs_api.approve(run.rc.run_id, ApprovalRequest(planVersion=version))
    events = await collect(run)
    assert text_of(events) == "A final checked deliverable."


async def test_final_planner_content_is_checked_and_corrected_before_publication(fake_llm):
    one_step(fake_llm)
    answers = iter(["BAD ASSEMBLY", "Correct final deliverable"])
    fake_llm.on("plan:assemble", lambda messages: next(answers))
    fake_llm.on("checker", lambda messages: json.dumps({"pass": "BAD ASSEMBLY" not in str(messages), "issues": "incorrect final content"}))
    run = await manager.start(req(mode="planner"))
    await waiting_plan(run)
    await run.rc.approvals.put(("approve", ""))
    events = await collect(run)
    assert text_of(events) == "Correct final deliverable"
    assert not any(e["type"] == "text" and "BAD ASSEMBLY" in e["delta"] for e in events)
    assert sum(c["stage"] == "plan:assemble" for c in fake_llm.calls) == 2


async def test_stop_retains_completed_step_content_and_remaining_tasks(fake_llm, monkeypatch):
    fake_llm.on("plan", {"title": "T", "final_format": "text", "steps": [
        {"task": "First", "kind": "easy"}, {"task": "Second", "kind": "easy", "needs": [0]}]})
    fake_llm.on("step", "PERSISTED_FIRST_RESULT").on("checker", {"pass": True})
    second = asyncio.Event()
    calls = 0

    async def slow(*args, stage="", **kwargs):
        nonlocal calls
        if stage == "step":
            calls += 1
            if calls == 2:
                second.set()
                await asyncio.Future()
        return await fake_llm(*args, stage=stage, **kwargs)

    monkeypatch.setattr(llm, "complete", slow)
    run = await manager.start(req(mode="planner"))
    await waiting_plan(run)
    await run.rc.approvals.put(("approve", ""))
    await asyncio.wait_for(second.wait(), 4)
    manager.stop(run.rc.run_id)
    await run.task
    saved = memory.ui_messages("c1")[-1]
    assert "PERSISTED_FIRST_RESULT" in saved["text"] and "Second" in saved["text"]
    assert saved["meta"]["planResults"][0]["result"] == "PERSISTED_FIRST_RESULT"


async def test_checker_never_silently_passes_unavailable_and_budget_stop(fake_llm, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr(llm, "ask_json", unavailable)
    result = await checker.check("question", "draft", ctx=llm.CallContext())
    assert not result.passed and not result.verified and "unavailable" in result.issues

    async def over_budget(*args, **kwargs):
        raise BudgetExceeded(0, 0, 1)
    monkeypatch.setattr(llm, "ask_json", over_budget)
    with pytest.raises(BudgetExceeded):
        await checker.check("question", "draft", ctx=llm.CallContext())


async def test_complete_final_answer_and_evidence_are_not_truncated(fake_llm):
    fake_llm.on("checker", {"pass": True})
    await checker.check("Q" * 3000, "D" * 10000 + "TAIL-DRAFT", excerpts="E" * 10000 + "TAIL-EVIDENCE", ctx=llm.CallContext())
    payload = str(fake_llm.calls[-1]["messages"])
    assert "TAIL-DRAFT" in payload and "TAIL-EVIDENCE" in payload


async def test_housekeeping_shares_question_budget_and_final_cost(fake_llm):
    fake_llm.on("answer", "Good answer").on("checker", {"pass": True})
    run = await manager.start(req())
    events = await collect(run)
    assert run.rc.house is run.rc.meter
    assert events[-1]["type"] == "done"
    cost = next(e for e in reversed(events) if e["type"] == "cost")
    assert cost["usd"] == pytest.approx(run.rc.meter.usd)
    assert memory.ui_messages("c1")[-1]["costUsd"] == pytest.approx(run.rc.meter.usd)


async def test_duplicate_run_id_does_not_replace_another_chat(fake_llm):
    fake_llm.on("answer", "Original answer").on("checker", {"pass": True})
    await collect(await manager.start(req()))
    with pytest.raises(ValueError, match="already been used"):
        await manager.start(req(chatId="c2"))
    assert memory.ui_messages("c1")[-1]["text"] == "Original answer"


async def test_clarification_applies_to_explicit_modes_and_long_requests(fake_llm):
    question = "Which deliverable should I create?"
    fake_llm.on("router", {"mode": "simple", "safe": True, "understood": False, "clarify": question})
    events = await collect(await manager.start(req("Please create the complete thing with all the details that we still have not defined", mode="planner")))
    assert text_of(events) == question
    assert not any(c["stage"] in {"plan", "step", "answer"} for c in fake_llm.calls)


async def test_clear_request_is_answered_even_if_the_small_model_adds_a_question(fake_llm):
    # Measured live: llama-3.1-8b attached "What are the team's goals?" to clear comparison questions.
    fake_llm.on("router", {"mode": "simple", "safe": True, "understood": True, "clarify": "What are your goals?"})
    fake_llm.on("answer", "Use an existing service.").on("checker", {"pass": True})
    events = await collect(await manager.start(req("Should a small team build its own search engine or use an existing service?", mode="simple")))
    assert not any(e["type"] == "clarify" for e in events)
    assert any(c["stage"] == "answer" for c in fake_llm.calls)


async def test_debate_late_failure_falls_back_to_simple(fake_llm, monkeypatch):
    fake_llm.on("thinker:judge", {"agree": False}).on("answer", "Simple fallback").on("checker", {"pass": True})
    number = 0

    async def fail_late(rc, progress, agents, *args):
        nonlocal number
        number += 1
        for i, agent in enumerate(agents):
            agent.answer = agent.first = "An agent result"
            agent.alive = number == 1 or i == 0
        return sum(a.alive for a in agents)

    monkeypatch.setattr(thinker, "run_round", fail_late)
    request = req(mode="thinker")
    request["team"].update(style="together", rounds=2)
    events = await collect(await manager.start(request))
    assert text_of(events) == "Simple fallback"
    assert not any(c["stage"] == "thinker:compose" for c in fake_llm.calls)


async def test_risky_permission_requires_current_explicit_answer(fake_llm):
    # A real Future and API response, without running any external tool/code.
    one_step(fake_llm)
    run = await manager.start(req(mode="planner"))
    await waiting_plan(run)
    pending = asyncio.create_task(run.rc.request_permission("run_code", {"code": "print(1)"}))
    while True:
        event = await asyncio.wait_for(run.rc.queue.get(), 4)
        if event["type"] == "permission":
            break
    await runs_api.permission(run.rc.run_id, PermissionRequest(id=event["id"], allow=False))
    assert await pending is False
    with pytest.raises(HTTPException):
        await runs_api.permission(run.rc.run_id, PermissionRequest(id=event["id"], allow=True))
    manager.stop(run.rc.run_id)
    await run.task


def test_replan_steps_cap_includes_completed_steps():
    from app.modes.planner.plan import normalize
    steps, _ = normalize({"steps": [{"task": str(i)} for i in range(20)]}, offset=19)
    assert len(steps) == 1


async def test_edit_of_replacement_plan_waits_for_actual_approval(fake_llm):
    from app.modes.planner.plan import Step
    one_step(fake_llm)
    request = req()
    memory.add_message("c1", "assistant", "", mid=request["id"])
    meter = CostMeter(1)
    rc = RunContext(request["id"], "c1", request, meter, memory.get_settings(), asyncio.Queue(), fresh_view("planner", "goal", {}, False), time.monotonic() + 30,
                    ctx=llm.CallContext(meter=meter))
    task = asyncio.create_task(planner._replan(rc, "Original goal", [Step("Failed", "done", "easy", status="failed")], {}, 0))
    first = None
    while not first:
        event = await asyncio.wait_for(rc.queue.get(), 4)
        if event["type"] == "plan" and event["awaitingApproval"]:
            first = event
    await rc.approvals.put(("edit", "Keep the original goal and simplify"))
    while True:
        event = await asyncio.wait_for(rc.queue.get(), 4)
        if event["type"] == "plan" and event["awaitingApproval"]:
            break
    assert not task.done() and event["version"] != first["version"]
    assert any("simplify" in str(c["messages"]) for c in fake_llm.calls if c["stage"] == "plan")
    await rc.approvals.put(("approve", ""))
    steps, _ = await task
    assert steps and all(s.status == "waiting" for s in steps)


async def test_failed_auto_simple_step_retries_with_team(fake_llm):
    one_step(fake_llm)
    fake_llm.on("step", "INITIAL WRONG DRAFT").on("thinker:agent", "Team evidence").on("thinker:compose", "TEAM CORRECTION")
    fake_llm.on("checker", lambda messages: json.dumps({"pass": "INITIAL WRONG DRAFT" not in str(messages), "issues": "wrong"}))
    run = await manager.start(req(mode="planner"))
    await waiting_plan(run)
    await run.rc.approvals.put(("approve", ""))
    events = await collect(run)
    assert sum(c["stage"] == "step" for c in fake_llm.calls) == 1
    assert sum(c["stage"] == "thinker:agent" for c in fake_llm.calls) == 3
    assert events[-1]["type"] == "done"


async def test_file_retry_checker_receives_newly_found_evidence(fake_llm, monkeypatch):
    from app import files
    built = SimpleNamespace(messages=[{"role": "system", "content": "rules"}, {"role": "user", "content": "question"}],
                            files=SimpleNamespace(mode="search", text="OLD EVIDENCE"), raw_tokens=100)
    async def build(*args, **kwargs):
        return built
    async def search(*args, **kwargs):
        return [{"text": "NEW PROOF p.7"}]
    monkeypatch.setattr(memory, "build", build)
    monkeypatch.setattr(files, "search_chunks", search)
    fake_llm.on("answer", "The code is47.").on("answer:retry", "The code is47 [manual p.7].")
    fake_llm.on("checker", lambda messages: json.dumps({"pass": "NEW PROOF" in str(messages), "unsupported": [] if "NEW PROOF" in str(messages) else ["code47"], "search": "code"}))
    events = await collect(await manager.start(req()))
    checks = [c for c in fake_llm.calls if c["stage"] == "checker"]
    assert len(checks) == 2 and "NEW PROOF" in str(checks[-1]["messages"])
    assert not any(e["type"] == "warning" and "unsupported" in e["message"] for e in events)


async def test_missing_plan_version_is_rejected_and_current_plan_is_reissued(fake_llm):
    one_step(fake_llm)
    run = await manager.start(req(mode="planner"))
    current = await waiting_plan(run)
    with pytest.raises(HTTPException) as missing:
        await runs_api.approve(run.rc.run_id)
    assert missing.value.status_code == 409
    reissued = await waiting_plan(run)
    assert reissued["version"] == current["version"] and run.rc.awaiting_approval
    assert not any(c["stage"] == "step" for c in fake_llm.calls)
    manager.stop(run.rc.run_id)
    await run.task


async def test_stop_during_memory_writer_persists_final_charges(fake_llm, monkeypatch):
    fake_llm.on("answer", "Completed answer").on("checker", {"pass": True})
    writing = asyncio.Event()

    async def writer(chat_id, user, answer, ctx):
        ctx.meter.add("memory:test", .004, 10, 10)
        writing.set()
        try:
            await asyncio.Future()
        finally:
            ctx.meter.add("memory:cancel", .002, 10, 10)

    monkeypatch.setattr(memory, "write_turn_memory", writer)
    run = await manager.start(req())
    await asyncio.wait_for(writing.wait(), 3)
    manager.stop(run.rc.run_id)
    await run.task
    saved = memory.ui_messages("c1")[-1]
    assert run.finished and saved["status"] == "stopped"
    assert saved["costUsd"] == pytest.approx(run.rc.meter.usd)
    assert saved["costUsd"] >= .006
    assert "Completed answer" in saved["text"]


async def test_deadline_includes_router_not_only_mode(fake_llm, monkeypatch):
    async def slow(*args, stage="", **kwargs):
        if stage == "router":
            await asyncio.sleep(1)
        return await fake_llm(*args, stage=stage, **kwargs)
    monkeypatch.setattr(llm, "complete", slow)
    run = await manager.start(req())
    run.rc.deadline = time.monotonic() + .02
    started = time.monotonic()
    events = await collect(run)
    assert time.monotonic() - started < .5
    assert "time limit" in text_of(events)
    assert not any(c["stage"] == "answer" for c in fake_llm.calls)


async def test_estimate_reports_cost_even_when_no_composer_is_affordable():
    from app.pipeline.estimate import estimate
    from app.llm import registry
    for model in registry.models.values():
        model.available = False
    result = await estimate(req(mode="thinker"), None)
    assert result["usd"] >= 0 and "composer" in result["breakdown"]


async def test_planner_file_envelope_is_data_and_actual_content_is_checked(fake_llm):
    from app import output
    from pathlib import Path
    one_step(fake_llm)
    fake_llm.on("plan", {"title": "sum_report", "final_format": "md", "steps": [{"task": "Calculate", "kind": "easy"}]})
    fake_llm.on("step", "1+2+3=6")
    fake_llm.on("plan:assemble", '```json\n{"name":"write_file","arguments":{"file_path":"../../outside.md","content":"# Sum\\nFINAL: 6"}}\n```')
    run = await manager.start(req(mode="planner"))
    await waiting_plan(run)
    await run.rc.approvals.put(("approve", ""))
    events = await collect(run)
    file = next(e["file"] for e in events if e["type"] == "output")
    artifact = output.get_artifact(file["id"])
    assert Path(artifact["path"]).read_text(encoding="utf-8") == "# Sum\nFINAL: 6"
    last_check = [c for c in fake_llm.calls if c["stage"] == "checker"][-1]
    assert "FINAL: 6" in str(last_check["messages"]) and "write_file" not in str(last_check["messages"])
    assert file["checked"]


async def test_output_tool_step_really_builds_file_without_another_model_call(fake_llm):
    one_step(fake_llm)
    fake_llm.on("plan", {"title": "sum_report", "final_format": "md", "steps": [
        {"task": "Write the result", "kind": "easy"},
        {"task": "Build the Markdown file", "kind": "tool", "tools": ["build_output"]}]})
    fake_llm.on("step", "# Sum\nFINAL: 6")
    run = await manager.start(req("Make a Markdown sum report", mode="planner"))
    await waiting_plan(run)
    await run.rc.approvals.put(("approve", ""))
    events = await collect(run)
    assert any(e["type"] == "output" and e["file"]["checked"] for e in events)
    assert sum(c["stage"] == "step" for c in fake_llm.calls) == 1
    assert not any(c["stage"] == "plan:assemble" for c in fake_llm.calls)
    assert run.rc.plan_steps[1].artifact and run.rc.plan_steps[1].needs == [0]


async def test_pdf_requested_page_count_matches_real_rendered_file(fake_llm):
    one_step(fake_llm)
    fake_llm.on("plan", {"title": "Two pages", "final_format": "pdf", "steps": [{"task": "Write", "kind": "easy"}]})
    fake_llm.on("plan:assemble", "# First page\nFirst section.\n<!-- pagebreak -->\n# Second page\nSecond section.")
    run = await manager.start(req("Create a 2-page PDF report", mode="planner"))
    await waiting_plan(run)
    await run.rc.approvals.put(("approve", ""))
    events = await collect(run)
    file = next(e["file"] for e in events if e["type"] == "output")
    assert file["pages"] == 2 and file["checked"]


async def test_stop_acknowledgement_includes_settled_cost(fake_llm, monkeypatch):
    fake_llm.on("answer", "Completed answer").on("checker", {"pass": True})
    writing = asyncio.Event()
    async def writer(chat_id, user, answer, ctx):
        writing.set()
        try:
            await asyncio.Future()
        finally:
            ctx.meter.add("memory:cancel", .002, 10, 10)
    monkeypatch.setattr(memory, "write_turn_memory", writer)
    run = await manager.start(req())
    await asyncio.wait_for(writing.wait(), 3)
    result = await runs_api.stop(run.rc.run_id)
    assert result["stopped"] and run.finished
    assert result["usd"] == pytest.approx(run.rc.meter.usd)
    assert memory.ui_messages("c1")[-1]["costUsd"] == result["usd"]


def test_invalid_settings_do_not_partially_save():
    original = memory.get_settings()
    with pytest.raises(ValueError):
        memory.update_settings({"longMemory": False, "monthBudget": "invalid"})
    assert memory.get_settings()["longMemory"] == original["longMemory"]
    with pytest.raises(ValueError):
        memory.update_settings({"tempChat": "false"})


async def test_planner_retry_uses_fresh_grounding_evidence(fake_llm, monkeypatch):
    from app import files
    one_step(fake_llm)
    built = SimpleNamespace(messages=[{"role": "system", "content": "rules"}, {"role": "user", "content": "question"}],
                            files=SimpleNamespace(mode="search", text="OLD EVIDENCE"), raw_tokens=100, tokens=100)
    async def build(*args, **kwargs):
        return built
    async def search(*args, **kwargs):
        return [{"text": "NEW_PROOF from manual p.7"}]
    monkeypatch.setattr(memory, "build", build)
    monkeypatch.setattr(files, "search_chunks", search)
    fake_llm.on("thinker:agent", "Grounded facts").on("thinker:compose", "Corrected step")
    def checking(messages):
        payload = messages[-1]["content"]
        missing = "QUESTION:\nDo it" in payload and "NEW_PROOF" not in payload
        return json.dumps({"pass": not missing, "unsupported": ["missing claim"] if missing else [], "search": "manual fact"})
    fake_llm.on("checker", checking)
    run = await manager.start(req(mode="planner"))
    await waiting_plan(run)
    await run.rc.approvals.put(("approve", ""))
    events = await collect(run)
    checks = [c for c in fake_llm.calls if c["stage"] == "checker"]
    assert any("NEW_PROOF" in str(c["messages"]) for c in checks)
    assert run.rc.plan_steps[0].status == "done"
    assert events[-1]["type"] == "done"
