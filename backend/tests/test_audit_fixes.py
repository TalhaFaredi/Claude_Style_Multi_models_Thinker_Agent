"""Regressions for defects found in the live audit of November 10, 2026 (real cheap models, isolated data).

1. qwen3.7-flash at thinking "low" spent the whole allowance on reasoning and returned empty text, so every
   Planner team step fell back to Simple ("Fewer than 2 agents answered").
2. A "1-page PDF" request rendered 2 pages and was delivered unchecked after three rewrites.
"""
from __future__ import annotations

import importlib

import pytest

from app import output
from app.core.costmeter import CostMeter
from app.llm import CallContext, ChatResult, Usage
from app.llm.registry import ModelInfo, registry

client = importlib.import_module("app.llm.client")


def thinking_model(mid="audit/thinker"):
    info = ModelInfo(mid, mid, "Audit", "openrouter", True, False, True, 100000, 0, 1000, featured=True)
    registry.models = {**registry.models, mid: info}
    return info


async def test_empty_answer_after_reasoning_is_asked_again_without_reasoning(monkeypatch):
    info, bodies = thinking_model(), []

    async def provider(info, body, *args):
        bodies.append(body.get("reasoning"))
        if body.get("reasoning", {}).get("enabled") is False:
            return ChatResult(text="Visible answer", usage=Usage(completion=10, cost=0.00001))
        return ChatResult(text="", reasoning="long hidden thoughts", finish="length", usage=Usage(completion=1724, reasoning=1724, cost=0.0003))

    monkeypatch.setattr(client, "_call_once", provider)
    meter = CostMeter(5.0)
    res = await client.complete(info.id, [{"role": "user", "content": "q"}], stage="test", ctx=CallContext(meter=meter),
                                max_tokens=100, thinking="low", allow_fallback=False)
    assert res.text == "Visible answer"
    assert bodies == [{"effort": "low"}, {"enabled": False}]
    assert meter.calls == 2 and meter.usd == pytest.approx(0.00031)   # both calls are paid and counted
    # The lesson is kept: the next call at this level goes straight to "no reasoning" instead of paying twice again.
    await client.complete(info.id, [{"role": "user", "content": "q"}], stage="test", ctx=CallContext(meter=meter),
                          max_tokens=100, thinking="low", allow_fallback=False)
    assert bodies[2:] == [{"enabled": False}] and meter.calls == 3


async def test_a_nonthinking_empty_answer_is_not_retried(monkeypatch):
    info, calls = thinking_model("audit/thinker-off"), []

    async def provider(info, body, *args):
        calls.append(1)
        return ChatResult(text="", usage=Usage(completion=1, cost=0.0))

    monkeypatch.setattr(client, "_call_once", provider)
    res = await client.complete(info.id, [], stage="test", ctx=CallContext(meter=CostMeter(5.0)), max_tokens=50, thinking="off", allow_fallback=False)
    assert res.text == "" and len(calls) == 1


def test_requested_pages_parsing():
    assert output.requested_pages("Make a 1-page PDF report on water", "pdf") == 1
    assert output.requested_pages("a 2 page pdf", "pdf") == 2
    assert output.requested_pages("Make a 1-page summary", "md") is None
    assert output.requested_pages("Make a PDF report", "pdf") is None


def test_fit_pdf_shrinks_slightly_long_text_to_the_requested_pages():
    text = "# Water report\n\n" + "\n\n".join(f"Paragraph {i}: " + "Water conservation protects supplies and lowers costs. " * 5 for i in range(14))
    plain = output.pdf_pages(output.fit_pdf("Report", text, None))
    fitted = output.pdf_pages(output.fit_pdf("Report", text, 1))
    assert plain == 2 and fitted == 1


def test_fit_pdf_never_cuts_content_that_cannot_fit():
    text = "\n\n".join("Long paragraph " + "word " * 120 for _ in range(30))
    assert output.pdf_pages(output.fit_pdf("Report", text, 1)) > 1   # still over: the page check reports it


def test_the_file_contains_the_final_draft_not_the_research_it_used():
    from app.modes.planner.plan import Step
    from app.modes.planner.steps import deliverable_parts
    research = Step(task="Research", done_test="facts", kind="easy")
    draft = Step(task="Draft", done_test="text", kind="hard", needs=[0])
    side = Step(task="Appendix", done_test="text", kind="easy")
    pdf = Step(task="PDF", done_test="file", kind="tool", needs=[0, 1, 2])
    assert deliverable_parts([research, draft, side, pdf], pdf) == [1, 2]


def test_output_step_is_checked_by_measuring_the_file():
    from app.modes.planner.steps import output_check
    assert output_check({"pages": 1}, 1).passed
    assert output_check({"pages": 1}, None).passed
    over = output_check({"pages": 3}, 1)
    assert not over.passed and "3 pages" in over.issues
    assert not output_check({"pages": 1, "warning": "The pdf format did not validate"}, 1).passed


async def test_checker_retries_an_unreadable_reply_and_accepts_text_booleans(fake_llm):
    from app.pipeline import checker
    replies = iter(["not json at all", '{"pass": "true", "issues": ""}'])
    fake_llm.on("checker", lambda messages: next(replies))
    result = await checker.check("Q?", "An answer.", ctx=CallContext(meter=CostMeter(1.0)))
    assert result.passed and result.verified
    assert sum(c["stage"] == "checker" for c in fake_llm.calls) == 2


async def test_checker_gives_up_after_two_unreadable_replies(fake_llm):
    from app.pipeline import checker
    fake_llm.on("checker", "still not json")
    result = await checker.check("Q?", "An answer.", ctx=CallContext(meter=CostMeter(1.0)))
    assert not result.passed and not result.verified


def test_markdown_rules_and_loose_lists_render_compactly():
    from pypdf import PdfReader
    import io
    doc = "# Title\n\n---\n\n" + "".join(f"- Bullet point number {i} about water.\n\n" for i in range(30)) + "---\n\nEnd."
    data = output.fit_pdf("T", doc, None)
    text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
    assert "---" not in text and output.pdf_pages(data) == 1
    from app.output.formats import to_html
    assert "<hr>" in to_html("T", doc) and "<p>---</p>" not in to_html("T", doc)


async def test_small_window_drops_optional_skills_instead_of_refusing_the_turn():
    # Measured live: at an 8k working window, rules + a 400-token skill exceeded the 5% rules share and every turn was refused.
    from app import memory
    from app.core import db
    db.set_setting("windowCap", 8000)
    skill = "<skills>\n" + "Guidance sentence for the skill. " * 120 + "\n</skills>"
    built = await memory.build("small-window-chat", "What is my project called?", "qwen/qwen3.7-flash", skills_text=skill)
    assert not any("Guidance sentence for the skill" in str(m["content"]) for m in built.messages), (built.window, built.parts)
    small = await memory.build("small-window-chat-2", "Hi", "qwen/qwen3.7-flash", skills_text="<skills>\nShort tip.\n</skills>")
    assert any("Short tip." in str(m["content"]) for m in small.messages)   # a skill that fits is kept
    assert built.messages[-1]["content"] == "What is my project called?"


async def test_checker_sees_the_remembered_facts_the_answer_used(fake_llm):
    # Measured live: without them, 12 of 12 memory answers failed their first check and a third ended as "I do not have access".
    from app import memory
    from app.pipeline.engine import manager
    from tests.test_pipeline import collect, req
    memory.add_fact("User's project is called Nimbus.", "earlier chat", None)
    fake_llm.on("answer", "Your project is called Nimbus.").on("checker", {"pass": True})
    await collect(await manager.start(req("What is my project called?", mode="simple")))
    check_call = next(c for c in fake_llm.calls if c["stage"] == "checker")
    payload = str(check_call["messages"])
    assert "CONVERSATION CONTEXT" in payload and "Nimbus" in payload.split("CONVERSATION CONTEXT", 1)[1]


def test_checker_context_keeps_memory_summary_and_recent_turns_only():
    from app import memory
    msgs = [{"role": "system", "content": "rules"}, {"role": "system", "content": "<documents>file</documents>"},
            {"role": "system", "content": "<memory>\n- fact\n</memory>"}, {"role": "system", "content": "<summary>\nolder\n</summary>"},
            {"role": "user", "content": "earlier question"}, {"role": "assistant", "content": "earlier answer"}, {"role": "user", "content": "new question"}]
    known = memory.checker_context(msgs)
    assert "- fact" in known and "older" in known and "earlier answer" in known
    assert "rules" not in known and "<documents>" not in known and "new question" not in known


@pytest.mark.parametrize("text,want", [
    ("Please remember: my favorite color is teal and my project is called Nimbus.", set()),   # got design advice live
    ("Why is the sky blue?", set()),
    ("Give me a list of fruits", set()),
    ("I have a plan to visit Paris, any tips?", set()),
    ("How many people live in Tokyo?", set()),
    ("What are some good ideas for dinner?", set()),
    ("Design a logo and color palette for my bakery brand", {"visual-design"}),
    ("What is the current price of Bitcoin?", {"web-research"}),
    ("Make a 6-month study plan for learning Spanish", {"writing-plans"}),
    ("Please humanize this LinkedIn post", {"humanizer"}),
])
def test_one_common_word_does_not_pick_a_skill(text, want):
    from app import skills
    got = {s.name for s in skills.select(text, mode="simple")}
    assert want <= got and (want or not got), got


def test_artifact_uses_the_requested_page_count():
    text = "# Water report\n\n" + "\n\n".join(f"Paragraph {i}: " + "Water conservation protects supplies and lowers costs. " * 5 for i in range(14))
    art = output.build_artifact(None, "Report", text, "pdf", pages_target=1)
    assert art["pages"] == 1 and art["format"] == "pdf"
