"""Context Builder and context meter (spec Part 2 sections 6 and 7).

Before every turn the window ("the desk") is rebuilt inside fixed budgets, in this order:

    1 rules            stable                  \   the cached prefix: identical turn to turn, so the
    2 files            stable while unchanged  /   provider bills it at ~10% of the input price
    3 memory           facts + ledger + recalled originals (spec Figure 8 order)
    4 summaries        stable between compacts
    5 recent turns     grows at the end
    6 skills           the skills picked for this question (they change, so they sit late, not in the prefix)
    7 new message      last: models use the start and the end of a prompt best

15% of the window is kept free for the answer. The meter is calibrated per chat against the provider's
real prompt-token count, so 70% / 85% / 95% mean what they say.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from app import prompts
from app.core import db
from app.core.config import ANSWER_RESERVE, FILES_BUDGET, LEVEL_ALARM, LEVEL_COMPACT, LEVEL_NOTICE, MEMORY_BUDGET
from app.core.tokens import IMAGE_TOKENS, estimate_tokens
from app.files import FileContext, cards_text, chat_readings, file_context, total_file_tokens
from app.llm import CallContext, ModelInfo, registry
from app.memory.archive import ensure_chat, get_chat
from app.memory.facts import relevant_facts
from app.memory.ledger import ledger_items
from app.memory.recall import recall_originals
from app.memory.settings import get_settings, long_memory_on

PART_LABELS = {"rules": "Rules and tools", "files": "Files", "memory": "Memory", "summary": "Summary", "recent": "Recent messages"}
RULES_SHARE = 0.05   # "Rules, tools: up to 5%" (spec Part 2 Figure 8); skills share this part


class ContextOverflow(Exception):
    """No provider request may be sent with a prompt that does not fit its model."""
    def __init__(self, tokens: int, usable: int, model: str, part: str | None = None):
        self.tokens, self.usable, self.model = tokens, usable, model
        area = f"The {part} part" if part else "This prompt"
        super().__init__(f"{area} needs about {tokens:,} tokens but {model} has {usable:,} allocated. "
                         "Summarize older turns, use a larger-window model, or start a new chat with a summary.")


@dataclass
class Built:
    messages: list[dict]
    parts: dict[str, int]
    window: int
    usable: int
    tokens: int
    percent: int
    level: str
    files: FileContext | None = None
    stable_tokens: int = 0     # prefix that stays identical turn to turn (cheap when cached)
    raw_tokens: int = 0        # estimate before calibration (compared with the provider's real count)

    def meter(self) -> dict:
        return {"percent": self.percent, "level": self.level, "windowTokens": self.window, "usableTokens": self.usable, "usedTokens": self.tokens,
                "parts": [{"label": PART_LABELS[k], "percent": round(v / self.usable * 100) if self.usable else 0, "tokens": v}
                          for k, v in self.parts.items() if k in PART_LABELS]}


def level_for(percent: int) -> str:
    return "compact" if percent >= LEVEL_COMPACT else "alarm" if percent >= LEVEL_ALARM else "notice" if percent >= LEVEL_NOTICE else "normal"


def window_for(model: ModelInfo, chat: dict | None) -> int:
    """Effective window: the model's, capped by the working-window setting (every turn re-sends the whole window)."""
    cap = (chat or {}).get("window_cap") or get_settings()["windowCap"]
    return max(2000, min(model.context, int(cap)))


def active_summaries(chat_id: str) -> list[dict]:
    return [dict(r) for r in db.q("SELECT * FROM summaries WHERE chat_id=? AND merged_into IS NULL ORDER BY from_seq", (chat_id,))]


def history(chat_id: str) -> list[dict]:
    """Turns still in the window (not yet swapped for a summary)."""
    return [dict(r) for r in db.q("SELECT * FROM messages WHERE chat_id=? AND role IN ('user','assistant') AND summarized_into IS NULL ORDER BY seq", (chat_id,))]


def _memory_block(chat: dict, text: str, budget_tokens: int) -> tuple[str, int]:
    """Facts + ledger + recalled originals, capped at the memory budget (10% of the window)."""
    lines: list[str] = []
    if long_memory_on(chat):   # a temporary chat does not read long-term memory either
        from app.memory.recall import date_range
        facts = relevant_facts(text, 6, include_history=date_range(text) is not None)
        if facts:
            lines.append("Facts about the user (dated):")
            lines += [f"- {f['text']} ({datetime.fromtimestamp(f['ts']).strftime('%Y-%m-%d')})" for f in facts]
            for f in facts:
                db.run("INSERT OR IGNORE INTO chat_facts(chat_id,fact_id) VALUES(?,?)", (chat["id"], f["id"]))
    led = ledger_items(chat["id"], only_open=True)
    if led:
        lines.append("Session ledger:")
        lines += [f"[{x['num']}] ({x['kind']}) {x['text']}" for x in led[-25:]]
    rec = recall_originals(chat["id"], text, summarized_only=True)
    if rec:
        lines.append("Original earlier messages that match the user's reference:")
        lines += [f"- ({datetime.fromtimestamp(m['ts']).strftime('%Y-%m-%d')}, {m['role']}) {m['content']}" for m in rec]
    out, used = [], 0
    for ln in lines:
        t = estimate_tokens(ln)
        if used + t > budget_tokens:
            break
        out.append(ln)
        used += t
    body = "\n".join(out)
    return (f"<memory>\n{body}\n</memory>" if body else ""), used


async def build(chat_id: str, new_text: str, model_id: str, *, tools: list[dict] | None = None, ctx: CallContext | None = None,
                lean: bool = False, with_files: bool = True, skills_text: str = "", images_ok: bool | None = None,
                files_override: FileContext | None = None, _fit_attempt: int = 0) -> Built:
    """Rebuild what the model reads this turn, inside a fixed budget (see the order in the module docstring)."""
    model = registry.get(model_id)
    chat = ensure_chat(chat_id)
    window = window_for(model, chat)
    usable = int(window * (1 - ANSWER_RESERVE))
    hist = history(chat_id)
    # The engine archives a turn before building; send that new user message exactly once.
    while hist and hist[-1]["role"] == "assistant" and not hist[-1]["content"]:
        hist.pop()
    if hist and hist[-1]["role"] == "user" and hist[-1]["content"] == new_text:
        hist.pop()
    sums = active_summaries(chat_id)

    rules = prompts.render("shared/system_rules")
    fctx = files_override
    if fctx is None and with_files:
        fctx = await file_context(chat_id, new_text, [{"role": m["role"], "content": m["content"]} for m in hist[-4:]], window, ctx,
                                  vision_model=model.vision if images_ok is None else images_ok)
    msgs: list[dict] = [{"role": "system", "content": rules}]
    parts = {"rules": estimate_tokens(rules) + (estimate_tokens(json.dumps(tools)) if tools else 0) + 8, "files": 0, "summary": 0, "memory": 0, "recent": 0}
    if skills_text and parts["rules"] + estimate_tokens(skills_text) > int(window * RULES_SHARE):
        skills_text = ""   # skills are optional guidance: on a small window they give way instead of blocking the turn
    if skills_text:   # sent right before the new message (below), so the cached prefix does not change with them
        parts["rules"] += estimate_tokens(skills_text)
    if fctx and fctx.text:
        msgs.append({"role": "system", "content": fctx.text})
        parts["files"] = fctx.tokens
    stable = sum(parts.values())
    mem_text, mem_tokens = _memory_block(chat, new_text, int(window * MEMORY_BUDGET))
    if mem_text:
        msgs.append({"role": "system", "content": mem_text})
        parts["memory"] = mem_tokens
    if sums:
        stext = ("<summary>\nEarlier parts of this chat were summarized (original messages are archived):\n"
                 + "\n\n".join(f"[messages {s['from_seq']}-{s['to_seq']}] {s['text']}" for s in sums) + "\n</summary>")
        msgs.append({"role": "system", "content": stext})
        parts["summary"] = estimate_tokens(stext)
    for m in hist:
        msgs.append({"role": m["role"], "content": m["content"]})
        parts["recent"] += m["tokens"] + 4
    if skills_text:
        msgs.append({"role": "system", "content": skills_text})
    user_content: str | list = new_text
    if fctx and fctx.images:
        user_content = [{"type": "text", "text": new_text}] + [{"type": "image_url", "image_url": {"url": u}} for u in fctx.images]
    msgs.append({"role": "user", "content": user_content})
    parts["recent"] += estimate_tokens(new_text) + 4 + (IMAGE_TOKENS * len(fctx.images) if fctx else 0)

    calib = float(chat.get("calib") or 1.0)
    total = int(sum(parts.values()) * calib)
    percent = int(round(total / usable * 100)) if usable else 100
    # Only parts the user can shrink (files by search, summaries by merging) have hard caps. The rules part cannot be
    # summarized away, so it only has to fit inside the whole window (measured: a hard 5% cap refused every turn at 8k).
    oversized_part = next(((part, int(window * share)) for part, share in (("files", FILES_BUDGET), ("summary", .05))
                           if parts[part] > int(window * share)), None)
    if total > usable or oversized_part:
        if ctx and get_settings()["autoCompact"] and _fit_attempt < 2:
            from app.memory.compaction import compact
            result = await compact(chat_id, model_id, ctx, target_percent=35)
            if result.ok and result.freed_tokens > 0:
                return await build(chat_id, new_text, model_id, tools=tools, ctx=ctx, lean=lean, with_files=with_files,
                                   skills_text=skills_text, images_ok=images_ok, files_override=files_override,
                                   _fit_attempt=_fit_attempt + 1)
        if oversized_part:
            raise ContextOverflow(parts[oversized_part[0]], oversized_part[1], model_id, oversized_part[0])
        raise ContextOverflow(total, usable, model_id)
    return Built(msgs, parts, window, usable, total, percent, level_for(percent), fctx, int(stable * calib), sum(parts.values()))


async def meter(chat_id: str, model_id: str) -> dict:
    """Context meter for the UI: how full the window is if the user sent a short message now, and its price."""
    chat = ensure_chat(chat_id)
    model = registry.get(model_id)
    usable = int(window_for(model, chat) * (1 - ANSWER_RESERVE))
    readings = chat_readings(chat_id)
    ftoks = min(total_file_tokens(chat_id) + estimate_tokens(cards_text(readings)), int(usable * FILES_BUDGET)) if readings else 0
    facts = relevant_facts("", 3) if long_memory_on(chat) else []
    led = ledger_items(chat_id, only_open=True)
    mem = min(int(usable * MEMORY_BUDGET), sum(estimate_tokens(f["text"]) + 8 for f in facts) + sum(estimate_tokens(x["text"]) + 8 for x in led[-25:]))
    parts = {"rules": estimate_tokens(prompts.render("shared/system_rules")) + 600, "files": ftoks,
             "summary": sum(s["tokens"] for s in active_summaries(chat_id)), "memory": mem,
             "recent": sum(m["tokens"] + 4 for m in history(chat_id))}
    calib = float(chat.get("calib") or 1.0)
    total = int(sum(parts.values()) * calib)
    percent = int(round(total / usable * 100)) if usable else 100
    out = Built([], parts, window_for(model, chat), usable, total, min(percent, 999), level_for(percent)).meter()
    stable = int((parts["rules"] + parts["files"] + parts["summary"] + parts["recent"]) * calib)
    out["nextMessageUsd"] = round(model.call_cost(total, 400), 6)
    out["nextMessageCachedUsd"] = round(model.call_cost(total, 400, cached=stable), 6)
    out["model"] = model_id
    return out


def checker_context(messages: list[dict], max_chars: int = 6000) -> str:
    """What the answer was allowed to rely on besides files: <memory>, <summary> and the recent turns.
    The Checker needs it, or it rejects every answer that uses a remembered fact as "invented"
    (measured Nov 10, 2026: 12 of 12 memory answers failed their first check; a third ended as "I do not have access")."""
    blocks = [str(m["content"]) for m in messages if m["role"] == "system" and str(m["content"]).startswith(("<memory>", "<summary>"))]
    turns = [m for m in messages[:-1] if m["role"] in ("user", "assistant") and isinstance(m["content"], str)][-6:]
    blocks += [f"{m['role']}: {m['content'][:600]}" for m in turns]
    return "\n\n".join(blocks)[-max_chars:]


def calibrate(chat_id: str, estimated_prompt: int, actual_prompt: int) -> None:
    """Keep the estimate honest: blend the provider's real prompt-token count into a per-chat ratio."""
    if estimated_prompt < 50 or actual_prompt <= 0:
        return
    chat = get_chat(chat_id)
    if not chat:
        return
    ratio = max(0.5, min(2.0, actual_prompt / estimated_prompt))
    db.run("UPDATE chats SET calib=? WHERE id=?", (round(0.6 * float(chat["calib"] or 1.0) + 0.4 * ratio, 4), chat_id))
