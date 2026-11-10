"""Memory: archive, ledger, long-term facts, Context Builder order, and CHECKED compaction (nothing is lost)."""
import json

from app import memory
from app.core import db
from app.core.costmeter import CostMeter
from app.llm import CallContext

CHAT = "c1"
SECRETS = ["$48,250", "2026-03-14", "dana@falcon-labs.org", "Dana Whitfield"]


def seed(n_filler: int = 24):
    memory.create_chat(chat_id=CHAT)
    memory.add_message(CHAT, "user", "My name is Dana Whitfield. Falcon budget is $48,250, deadline 2026-03-14, email dana@falcon-labs.org.")
    memory.add_message(CHAT, "assistant", "Noted: Dana Whitfield, Falcon budget $48,250, deadline 2026-03-14.")
    for i in range(n_filler):
        memory.add_message(CHAT, "user" if i % 2 == 0 else "assistant", f"filler message number {i} about topic {i} " + "word " * 60)


def ctx():
    return CallContext(meter=CostMeter(budget=1.0), chat_id=CHAT, run_id="t")


async def test_compaction_keeps_every_critical_detail_even_when_the_summary_drops_them(fake_llm):
    seed()
    fake_llm.on("compact:ledger", {"ops": [{"op": "add", "type": "goal", "text": "Finish Falcon", "src": 1}]})
    fake_llm.on("compact:summary", "The user talked about a project and some filler topics.")   # a LOSSY summary: drops every number and name
    fake_llm.on("compact:redo", "Still a vague summary.")
    steps = []
    res = await memory.compact(CHAT, "qwen/qwen3.7-flash", ctx(), lambda s: steps.append(s))
    assert res.ok and steps == [0, 1, 2, 3, 4]                     # the four checked steps, then done
    summ = db.one("SELECT * FROM summaries WHERE chat_id=?", (CHAT,))
    kept = summ["text"] + " ".join(x["text"] for x in memory.ledger_items(CHAT))
    for secret in SECRETS:                                          # the CHECK re-attaches what the model lost
        assert secret in kept, secret
    assert res.preserved_extra > 0
    total = db.one("SELECT COUNT(*) n FROM messages WHERE chat_id=?", (CHAT,))["n"]
    assert total == 26                                              # nothing deleted: originals stay in the Archive
    assert db.one("SELECT COUNT(*) n FROM msg_fts WHERE chat_id=?", (CHAT,))["n"] == 26   # and stay searchable


async def test_last_ten_turns_and_pinned_messages_are_never_compacted(fake_llm):
    seed()
    db.run("UPDATE messages SET pinned=1 WHERE seq=3")
    fake_llm.on("compact:ledger", {"ops": []}).on("compact:summary", "summary " + " ".join(SECRETS))
    await memory.compact(CHAT, "qwen/qwen3.7-flash", ctx())
    active = [r["seq"] for r in db.q("SELECT seq FROM messages WHERE chat_id=? AND summarized_into IS NULL", (CHAT,))]
    assert set(range(17, 27)) <= set(active)                        # the last 10 stay in the window
    assert 3 in active                                              # pinned stays


async def test_compaction_refuses_when_nothing_is_old_enough(fake_llm):
    memory.create_chat(chat_id=CHAT)
    for i in range(6):
        memory.add_message(CHAT, "user", f"m{i}")
    res = await memory.compact(CHAT, "qwen/qwen3.7-flash", ctx())
    assert not res.ok and "last 10" in res.reason


async def test_context_builder_order_is_stable_parts_first_and_new_message_last(fake_llm):
    seed(4)
    db.run("INSERT INTO summaries(chat_id,from_seq,to_seq,text,seqs,tokens,ts) VALUES(?,?,?,?,?,?,?)", (CHAT, 1, 2, "old summary", json.dumps([1, 2]), 5, db.now()))
    db.run("UPDATE messages SET summarized_into=1 WHERE seq<=2")
    memory.add_fact("Dana likes short answers", "chat", CHAT)
    built = await memory.build(CHAT, "What does Dana like?", "qwen/qwen3.7-flash", ctx=ctx())
    roles = [(m["role"], str(m["content"])[:12]) for m in built.messages]
    assert roles[0][0] == "system" and "careful" in str(built.messages[0]["content"])        # rules first
    sys_blocks = [i for i, m in enumerate(built.messages) if m["role"] == "system"]
    assert "<memory>" in built.messages[sys_blocks[1]]["content"]                             # diagram: memory before summary
    assert "<summary>" in built.messages[sys_blocks[2]]["content"]                            # summary before recent turns
    assert sys_blocks[-1] < min(i for i, m in enumerate(built.messages) if m["role"] in ("user", "assistant"))
    assert built.messages[-1] == {"role": "user", "content": "What does Dana like?"}          # new message last
    assert built.parts["summary"] > 0 and built.parts["memory"] > 0 and built.parts["recent"] > 0


def test_a_changed_fact_is_marked_replaced_with_the_date_not_deleted():
    old = memory.add_fact("Budget is $5", "chat", None)
    new = memory.add_fact("Budget is $20", "chat", None, replaces=old)
    cur = [f["text"] for f in memory.list_facts()]
    hist = {f["text"]: f for f in memory.list_facts(include_history=True)}
    assert cur == ["Budget is $20"]
    assert hist["Budget is $5"]["replaced"] and hist["Budget is $5"]["replacedOn"]
    assert new != old


def test_delete_chat_asks_about_memories_and_removes_every_store():
    seed(2)
    memory.add_fact("fact from this chat", "chat", CHAT)
    memory.ledger_apply(CHAT, [{"op": "add", "type": "goal", "text": "x"}])
    out = memory.delete_chat(CHAT, delete_memories=False)
    assert out["memoriesKept"] and memory.list_facts()                      # user chose to keep the memories
    assert db.one("SELECT COUNT(*) n FROM messages WHERE chat_id=?", (CHAT,))["n"] == 0
    assert db.one("SELECT COUNT(*) n FROM msg_fts WHERE chat_id=?", (CHAT,))["n"] == 0
    assert db.one("SELECT COUNT(*) n FROM ledger WHERE chat_id=?", (CHAT,))["n"] == 0
    seed(2)
    memory.add_fact("another fact", "chat", CHAT)
    memory.delete_chat(CHAT, delete_memories=True)
    assert all("another fact" not in f["text"] for f in memory.list_facts())


def test_recall_finds_original_messages_for_as_i_said_last_week():
    memory.create_chat(chat_id=CHAT)
    week_ago = db.now() - 8 * 86400
    memory.add_message(CHAT, "user", "The vendor contract number is VX-9917", ts=week_ago)
    memory.add_message(CHAT, "user", "something recent about lunch")
    found = memory.recall_originals(CHAT, "As I said last week, what was the vendor contract number?")
    assert any("VX-9917" in m["content"] for m in found)
    assert memory.recall_originals(CHAT, "what is the vendor contract number?") == []   # no time reference: not a recall


def test_settings_are_clamped_and_defaults_are_safe():
    assert memory.get_settings()["autoCompact"] is True and memory.get_settings()["reader"] == "auto"
    assert memory.update_settings({"windowCap": 10})["windowCap"] == 4000
    assert "evil" not in memory.update_settings({"evil": 1})


async def test_temporary_chat_writes_nothing_to_long_term_memory(fake_llm):
    memory.create_chat(chat_id=CHAT, temp=True)
    fake_llm.on("memory:facts", {"facts": [{"text": "User likes tea", "replaces": None}]})
    out = await memory.write_turn_memory(CHAT, "My favorite drink is tea and I always drink it", "ok", ctx())
    assert out == {"skipped": True} and memory.list_facts() == []              # C41
