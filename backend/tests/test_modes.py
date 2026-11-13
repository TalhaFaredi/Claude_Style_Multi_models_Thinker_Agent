"""The user picks the mode and the model; nothing else may answer in their place. There is no Auto mode."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app import memory
from app.api.schemas import EstimateRequest, RunRequest
from app.core import config
from app.pipeline import estimate as estimator
from app.pipeline.engine import manager
from tests.test_pipeline import collect, req, text_of

UNCLEAR = {"safe": True, "understood": False, "clarify": "What do you need help with?"}


async def test_simple_mode_is_always_answered_by_the_selected_model(fake_llm):
    """Reported live: "hi" in Simple with DeepSeek selected was answered by the helper's question, so the selected
    model never ran and the cost list showed only the helper."""
    fake_llm.on("router", UNCLEAR).on("answer", "Hello! How can I help?").on("checker", {"pass": True})
    events = await collect(await manager.start(req("hi", mode="simple")))
    assert text_of(events) == "Hello! How can I help?"
    assert not any(e["type"] == "clarify" for e in events)
    answer_calls = [c for c in fake_llm.calls if c["stage"] == "answer"]
    assert len(answer_calls) == 1 and answer_calls[0]["model"] == req()["simple"]["model"]
    assert memory.ui_messages("c1")[-1].get("clarify") is not True


async def test_helper_question_before_a_team_run_is_marked_as_such(fake_llm):
    fake_llm.on("router", UNCLEAR)
    events = await collect(await manager.start(req("help", mode="thinker")))
    assert text_of(events) == UNCLEAR["clarify"]
    assert not any(c["stage"].startswith("thinker") for c in fake_llm.calls)   # no team was paid for
    assert memory.ui_messages("c1")[-1]["clarify"] is True                    # the UI can say who asked


async def test_input_check_can_be_switched_off(fake_llm, monkeypatch):
    monkeypatch.setattr(config, "INPUT_CHECK", False)
    fake_llm.on("answer", "Four.").on("checker", {"pass": True})
    events = await collect(await manager.start(req("What is 2 + 2?")))
    assert text_of(events) == "Four."
    assert not any(c["stage"].startswith("router") for c in fake_llm.calls)
    assert "input check" not in (await estimator.estimate(req(), None))["breakdown"]


async def test_unsafe_requests_are_still_refused_in_simple(fake_llm):
    fake_llm.on("router", {"safe": False, "understood": True}).on("router:safety", {"safe": False, "understood": True})
    events = await collect(await manager.start(req("an unsafe request")))
    assert not any(c["stage"] == "answer" for c in fake_llm.calls)
    assert text_of(events)


def test_auto_is_not_a_mode_any_more():
    base = {"id": "r", "chatId": "c", "prompt": "hi", "simple": {"model": "m"}, "team": {"model": "m"}}
    assert RunRequest(**base).mode == "simple"                       # the default
    assert RunRequest(**base, mode="auto").mode == "simple"          # an old client's value is read as Simple
    assert EstimateRequest(**{k: v for k, v in base.items() if k not in ("id", "chatId")}, mode="auto").mode == "simple"
    assert RunRequest(**base, mode="planner").mode == "planner"
    with pytest.raises(ValidationError):
        RunRequest(**base, mode="smart")


async def test_estimate_prices_the_selected_mode_only(fake_llm):
    simple = await estimator.estimate(req("Make a 2-page PDF report on solar power", mode="simple"), None)
    assert simple["kind"] == "simple" and "plan" not in simple["breakdown"]   # the wording no longer changes the mode
    assert (await estimator.estimate(req("hi", mode="planner"), None))["kind"] == "planner"
    assert (await estimator.estimate({**req("hi"), "mode": "auto"}, None))["kind"] == "simple"


async def test_a_run_never_reports_auto(fake_llm):
    fake_llm.on("answer", "ok").on("checker", {"pass": True})
    events = await collect(await manager.start({**req("hi"), "mode": "auto"}))
    route = next(e for e in events if e["type"] == "route")
    assert route == {"type": "route", "kind": "simple", "reason": ""}
    assert memory.ui_messages("c1")[-1]["auto"] is False
