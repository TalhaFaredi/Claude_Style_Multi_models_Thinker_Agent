"""Safe compaction, like Claude's auto-compact, but checked (spec Part 2 Figure 9).

At 95% (or when the user presses Summarize):
  0. pick old turns: not pinned and not in the last 10 turns
  1. save the facts: small edits to the numbered ledger
  2. summarize: a block summary with its message numbers
  3. check: are all numbers, names, dates and ids kept? no -> redo with the list (max 2), then attach
     whatever is still missing word for word ("Preserved details")
  4. swap: the summary replaces those turns in the window
Nothing is deleted: the originals stay in the Archive and stay searchable.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from app import llm, prompts
from app.core import config, db
from app.core.config import ANSWER_RESERVE, KEEP_LAST_TURNS, SUMMARY_BUDGET
from app.core.tokens import estimate_tokens
from app.llm import CallContext, registry
from app.memory.archive import ensure_chat
from app.memory.context import active_summaries, history, meter, window_for
from app.memory.ledger import ledger_apply, ledger_items

# ------------------------------------------------------------------ the check: what a summary must not lose

_NUM = re.compile(r"[$€£]?\d[\d,]*(?:\.\d+)?%?")
_DATE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}(?:, \d{4})?)\b")
_NAME = re.compile(r"\b[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,}){0,3}\b")
_IDENT = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b|https?://\S+|\b[A-Za-z]+[_-]\w*\d\w*\b")
_NOT_NAMES = {"the", "this", "that", "there", "here", "what", "when", "where", "which", "while", "with"}


def critical_items(text: str) -> set[str]:
    """Numbers, dates, names, emails, links and ids (spec: "numbers, names, dates all kept?")."""
    items: set[str] = set()
    for m in _NUM.findall(text):
        digits = re.sub(r"\D", "", m)
        if digits:
            items.add(m.strip(",."))
    items.update(_DATE.findall(text))
    items.update(n for n in _NAME.findall(text) if n.split()[0].lower() not in _NOT_NAMES)
    items.update(m.rstrip(".,)") for m in _IDENT.findall(text))
    return {i for i in items if i}


def _norm(s: str) -> str:
    return re.sub(r"[\s,]+", " ", s.lower())


def missing_items(source: str, kept: str) -> list[str]:
    k = _norm(kept)
    return sorted(i for i in critical_items(source) if _norm(i) not in k)


# ------------------------------------------------------------------ compaction

ProgressCb = Callable[[int], Awaitable[None] | None]


@dataclass
class CompactResult:
    ok: bool
    reason: str = ""
    summarized: int = 0
    ledger_edits: int = 0
    freed_tokens: int = 0
    preserved_extra: int = 0
    block_id: int | None = None
    percent_after: int = 0


async def _progress(cb: ProgressCb | None, step: int) -> None:
    if cb:
        r = cb(step)
        if hasattr(r, "__await__"):
            await r


def _pick_turns(chat_id: str, usable: int, target_percent: int) -> list[dict]:
    """Step 0: the oldest turns, outside the last 10 and not pinned, until the window is back to the target."""
    hist = history(chat_id)
    candidates = [m for m in hist[:-KEEP_LAST_TURNS] if not m["pinned"]] if len(hist) > KEEP_LAST_TURNS else []
    other = sum(estimate_tokens(m["content"]) + 4 for m in hist[-KEEP_LAST_TURNS:]) + sum(s["tokens"] for s in active_summaries(chat_id))
    picked: list[dict] = []
    for m in candidates:
        picked.append(m)
        remaining = sum(x["tokens"] + 4 for x in candidates[len(picked):]) + other
        if remaining / usable * 100 <= target_percent and len(picked) >= 2:
            break
    if len(picked) % 2 == 1 and len(picked) < len(candidates):
        picked.append(candidates[len(picked)])   # keep user/assistant pairs together
    return picked


async def _save_to_ledger(chat_id: str, source: str, first_seq: int, ctx: CallContext) -> int:
    ledger_text = "\n".join(f"[{x['num']}] ({x['kind']}, {x['status']}) {x['text']}" for x in ledger_items(chat_id)) or "(empty)"
    try:
        data, _ = await llm.ask_json(config.WRITER_MODEL, prompts.render("memory/ledger"), f"Current ledger:\n{ledger_text}\n\nMessages:\n{source}",
                                     stage="compact:ledger", ctx=ctx, max_tokens=700)
        return ledger_apply(chat_id, (data or {}).get("ops", [])[:12] if isinstance(data, dict) else [], first_seq)
    except Exception:
        return 0


async def _summarize(source: str, ctx: CallContext, missing: list[str] | None = None) -> str:
    user = source + (f"\n\n{prompts.render('memory/summary_redo', missing=', '.join(missing))}" if missing else "")
    try:
        res = await llm.complete(config.WRITER_MODEL, [{"role": "system", "content": prompts.render("memory/summary")}, {"role": "user", "content": user}],
                                 stage="compact:redo" if missing else "compact:summary", ctx=ctx, temperature=0.0 if missing else 0.1,
                                 max_tokens=1100 if missing else 900)
        return res.text.strip()
    except Exception:
        return ""


async def compact(chat_id: str, model_id: str, ctx: CallContext, progress: ProgressCb | None = None, target_percent: int = 45) -> CompactResult:
    usable = int(window_for(registry.get(model_id), ensure_chat(chat_id)) * (1 - ANSWER_RESERVE))

    await _progress(progress, 0)
    picked = _pick_turns(chat_id, usable, target_percent)
    if not picked:
        await _progress(progress, 4)
        return CompactResult(False, "Nothing older than the last 10 turns can be summarized. If files fill the window, ask a narrower question so search mode is used.")
    source = "\n".join(f"[#{m['seq']} {m['role']}] {m['content']}" for m in picked)
    seqs = [m["seq"] for m in picked]

    await _progress(progress, 1)
    n_edits = await _save_to_ledger(chat_id, source, seqs[0], ctx)

    await _progress(progress, 2)
    summary = await _summarize(source, ctx)

    await _progress(progress, 3)
    for _ in range(2):
        miss = missing_items(source, summary + "\n" + "\n".join(x["text"] for x in ledger_items(chat_id)))
        if not miss or not summary:
            break
        summary = await _summarize(source, ctx, miss) or summary
    if not summary:
        # Failure is explicit and leaves the working history untouched. A truncated fallback is unsafe.
        return CompactResult(False, "The summary model could not produce a checked summary. Original messages were kept.")
    miss = missing_items(source, summary + "\n" + "\n".join(x["text"] for x in ledger_items(chat_id)))
    if miss:
        # Keep the original factual statement, not just a disconnected number/name. No item limit:
        # a dense source may refuse to fit later, but must never lose details while reporting success.
        statements = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", source) if s.strip()]
        keep = [s for s in statements if any(_norm(i) in _norm(s) for i in miss)]
        summary += "\nPreserved original details:\n" + "\n".join(dict.fromkeys(keep))
    final_missing = missing_items(source, summary + "\n" + "\n".join(x["text"] for x in ledger_items(chat_id)))
    if final_missing:
        return CompactResult(False, "The summary could not preserve every checked detail. Original messages were kept.")
    with db.tx() as c:
        sid = c.execute("INSERT INTO summaries(chat_id,from_seq,to_seq,text,seqs,tokens,ts) VALUES(?,?,?,?,?,?,?)",
                        (chat_id, seqs[0], seqs[-1], summary, json.dumps(seqs), estimate_tokens(summary), db.now())).lastrowid
        c.executemany("UPDATE messages SET summarized_into=? WHERE id=?", [(sid, m["id"]) for m in picked])
    await _merge_if_big(chat_id, int(usable * SUMMARY_BUDGET), ctx)
    await _progress(progress, 4)
    after = await meter(chat_id, model_id)
    freed = sum(m["tokens"] + 4 for m in picked)
    return CompactResult(True, "", len(picked), n_edits, max(0, freed - estimate_tokens(summary)), len(miss), sid, after["percent"])


async def _merge_if_big(chat_id: str, budget_tokens: int, ctx: CallContext) -> None:
    """Summaries have their own 5% budget: when they outgrow it, fold the oldest into one block (never lossy)."""
    sums = active_summaries(chat_id)
    if len(sums) < 2 or sum(s["tokens"] for s in sums) <= budget_tokens:
        return
    old = sums[:-1]
    text = "\n\n".join(s["text"] for s in old)
    try:
        res = await llm.complete(config.WRITER_MODEL, [{"role": "system", "content": prompts.render("memory/merge")}, {"role": "user", "content": text[:30000]}],
                                 stage="compact:merge", ctx=ctx, temperature=0.0, max_tokens=900)
        merged = res.text.strip()
    except Exception:
        return
    if not merged or missing_items(text, merged):
        return
    seqs = [q for s in old for q in json.loads(s["seqs"])]
    with db.tx() as c:
        mid = c.execute("INSERT INTO summaries(chat_id,from_seq,to_seq,text,seqs,tokens,ts) VALUES(?,?,?,?,?,?,?)",
                        (chat_id, old[0]["from_seq"], old[-1]["to_seq"], merged, json.dumps(seqs), estimate_tokens(merged), db.now())).lastrowid
        c.executemany("UPDATE summaries SET merged_into=? WHERE id=?", [(mid, s["id"]) for s in old])


async def fork_with_summary(chat_id: str, model_id: str, ctx: CallContext, title: str | None = None) -> dict:
    """Start a new chat with a checked handover; originals remain in the source archive."""
    from app.memory.archive import create_chat, get_chat, delete_chat
    from app.files import link
    source_chat = get_chat(chat_id)
    if not source_chat:
        raise ValueError("Unknown chat")
    rows = db.q("SELECT * FROM messages WHERE chat_id=? ORDER BY seq", (chat_id,))
    source = "\n".join(f"[#{r['seq']} {r['role']}] {r['content']}" for r in rows if r["role"] in ("user", "assistant"))
    summary = await _summarize(source, ctx)
    if not summary:
        raise ValueError("Could not create a checked handover; the original chat is unchanged.")
    missing = missing_items(source, summary)
    if missing:
        statements = [s for s in re.split(r"(?<=[.!?])\s+|\n", source) if any(_norm(i) in _norm(s) for i in missing)]
        summary += "\nPreserved original details:\n" + "\n".join(dict.fromkeys(statements))
    if missing_items(source, summary):
        raise ValueError("The handover could not preserve all checked details.")
    chat = create_chat(title or f"{source_chat['title']} (continued)", temp=bool(source_chat["temp"]))
    cid = chat["id"]
    db.run("INSERT INTO summaries(chat_id,from_seq,to_seq,text,seqs,tokens,ts) VALUES(?,?,?,?,?,?,?)",
           (cid, 0, 0, f"Handover from chat {chat_id}; originals remain searchable there.\n{summary}", "[]", estimate_tokens(summary), db.now()))
    for item in ledger_items(chat_id):
        db.run("INSERT INTO ledger(chat_id,num,kind,text,src_seq,status,ts) VALUES(?,?,?,?,?,?,?)",
               (cid, item["num"], item["kind"], item["text"], item["src_seq"], item["status"], item["ts"]))
    for row in db.q("SELECT fingerprint,reader FROM file_chats WHERE chat_id=?", (chat_id,)):
        link(cid, row["fingerprint"], row["reader"])
    for row in db.q("SELECT fact_id FROM chat_facts WHERE chat_id=? UNION SELECT id FROM facts WHERE chat_id=?", (chat_id, chat_id)):
        db.run("INSERT OR IGNORE INTO chat_facts(chat_id,fact_id) VALUES(?,?)", (cid, row[0]))
    try:
        from app.memory.context import build
        built = await build(cid, "Continue from the handover.", model_id, with_files=True)
    except Exception:
        delete_chat(cid, delete_memories=False)
        raise
    return {"chatId": cid, "sourceChatId": chat_id, "summary": summary, "context": built.meter(),
            "costUsd": round(ctx.meter.usd, 6) if ctx.meter else 0.0}
