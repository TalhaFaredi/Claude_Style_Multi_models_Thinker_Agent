"""Regressions from the flow audit of November 11, 2026: debate revisions, memory noise and text-file decoding."""
from __future__ import annotations

from app import memory
from app.files.analysis import analyze
from app.files.readers import extract_text_pages
from app.memory.ledger import ledger_items, update_turn_ledger
from app.pipeline.engine import manager
from tests.test_pipeline import collect, req, text_of

TEAM = {"source": "same", "model": "meta-llama/llama-3.1-8b-instruct", "agents": 2, "mixed": [], "style": "together", "rounds": 2, "composer": "auto"}


async def test_a_revising_agent_sees_its_own_earlier_answer(fake_llm):
    fake_llm.on("thinker:agent", lambda messages: "Unchanged" if "shared board" in str(messages[-1]["content"]) else "Round one answer.")
    fake_llm.on("thinker:judge", {"agree": False}).on("thinker:compose", "Merged answer.").on("checker", {"pass": True})
    events = await collect(await manager.start(req("Should we use A or B?", mode="thinker", team=TEAM)))
    revisions = [c for c in fake_llm.calls if c["stage"] == "thinker:agent" and "shared board" in str(c["messages"][-1]["content"])]
    assert len(revisions) == 2
    for call in revisions:
        assert call["messages"][-2] == {"role": "assistant", "content": "Round one answer."}
        assert call["messages"][-3]["content"] == "Should we use A or B?"        # the question itself is untouched
    assert not any(c["stage"] == "thinker:change" for c in fake_llm.calls)       # "Unchanged" alone needs no extra paid call
    assert text_of(events) == "Merged answer."


async def test_plain_questions_cost_no_ledger_call_and_questions_are_not_saved_as_decisions(fake_llm):
    memory.create_chat(chat_id="c1")
    assert await update_turn_ledger("c1", "who won the asia cup in 2012?", None) == 0
    assert not any(c["stage"] == "memory:ledger" for c in fake_llm.calls)
    fake_llm.on("memory:ledger", "not json")                                     # the writer failed: the safety net saves statements
    await update_turn_ledger("c1", "My budget is $48,250. What is my best option?", None)
    assert [x["text"] for x in ledger_items("c1")] == ["My budget is $48,250."]


async def test_recall_does_not_repeat_messages_still_in_the_window(fake_llm):
    memory.create_chat(chat_id="c1")
    memory.add_message("c1", "user", "The Falcon budget is $48,250.")
    memory.add_message("c1", "assistant", "Noted.")
    question = "As I said earlier, what is the Falcon budget?"
    memory.add_message("c1", "user", question)                                   # the engine archives it before building
    built = await memory.build("c1", question, "qwen/qwen3.7-flash")
    assert not any("Original earlier messages" in str(m["content"]) for m in built.messages)
    assert sum("$48,250" in str(m["content"]) for m in built.messages) == 1


def test_windows_text_files_are_read_as_text_not_as_scans():
    cp1252 = "Café résumé: the naïve plan costs €500 and ships in 3 days.".encode("cp1252")
    assert extract_text_pages("notes.txt", cp1252)[0][0].startswith("Café résumé")
    assert analyze("notes.txt", cp1252)[0].kind == "text"
    utf16 = "Budget is 5000 rupees for the whole project team.".encode("utf-16")
    assert "5000 rupees" in extract_text_pages("notes.txt", utf16)[0][0]
    assert analyze("blob.txt", bytes(range(256)) * 4)[0].kind == "scan"          # real binary is still flagged, never shown as text
