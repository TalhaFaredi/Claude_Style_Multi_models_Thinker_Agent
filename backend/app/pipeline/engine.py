"""Runs one question through the five stages, and manages live runs (start, stop, approvals).

  save the user message -> 1 gateway -> context check (compact first at 95%, C37/C38) -> 2 router
  -> Budget Guard warning (C7) -> 3 mode (with 4 Checker inside) -> 5 final check -> save the answer
  -> cost + context events -> auto-compact at 95% -> Memory Writer in the background -> done

A run always ends: with an answer, a partial result with a warning, or a clear error (C20).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app import files, memory, output
from app.core import config, db, usage
from app.core.config import PLANNER_TIMEOUT_S, RUN_TIMEOUT_S
from app.core.costmeter import BudgetExceeded, CostMeter, usd
from app.core.privacy import safe_message
from app.llm import CallContext, LLMError, registry
from app.modes.common import Result
from app.modes.planner import run_planner
from app.modes.simple import run_simple
from app.modes.thinker import run_thinker
from app.pipeline import estimate, gateway, router
from app.pipeline.runtime import RunContext, fresh_view

log = logging.getLogger("engine")


@dataclass
class Run:
    rc: RunContext
    task: asyncio.Task | None = None
    finished: bool = False
    created: float = field(default_factory=time.monotonic)


class RunManager:
    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    async def start(self, req: dict) -> Run:
        if req["id"] in self.runs or db.one("SELECT id FROM messages WHERE id=?", (req["id"],)):
            raise ValueError("This run ID has already been used. Start a new run with a new ID.")
        if any(not r.finished and r.rc.chat_id == req["chatId"] for r in self.runs.values()):
            raise ValueError("A question is already running in this chat")
        budget = req["budgetUsd"]   # includes the explicitly approved one-question cap
        meter = CostMeter(budget=budget)
        kind = req["mode"] if req["mode"] != "auto" else "simple"
        view = fresh_view(kind, req["prompt"], {"simple": req["simple"], "team": req["team"], "runIn": req["runIn"]}, req["mode"] == "auto")
        timeout = PLANNER_TIMEOUT_S if req["mode"] in ("planner", "auto") else RUN_TIMEOUT_S
        holder: dict[str, RunContext] = {}
        ctx = CallContext(meter=meter, chat_id=req["chatId"], run_id=req["id"],
                          on_switch=lambda a, b: holder["rc"].status(f"{registry.get(a).name} failed, switching to {registry.get(b).name}"),
                          on_notice=lambda message: holder["rc"].status(message),
                          on_event=lambda event: holder["rc"].emit(event))
        rc = RunContext(run_id=req["id"], chat_id=req["chatId"], req=req, meter=meter, settings=memory.get_settings(), queue=asyncio.Queue(),
                        view=view, deadline=time.monotonic() + timeout, ctx=ctx, house=meter)
        holder["rc"] = rc
        run = Run(rc)
        self.runs[req["id"]] = run
        run.task = asyncio.create_task(self._wrap(run))
        return run

    async def _wrap(self, run: Run) -> None:
        try:
            await execute(run.rc)
        except asyncio.CancelledError:
            # Stop may arrive during post-answer compaction or memory writing too.
            run.rc.view["status"] = "stopped"
            run.rc.view["text"] = run.rc.partial_text("you pressed Stop")
        finally:
            rc = run.rc
            rc.awaiting_approval = False
            for pending in rc.permissions.values():
                if not pending.done():
                    pending.cancel()
            rc.view["costUsd"], rc.view["calls"] = round(rc.meter.usd, 6), rc.meter.calls
            rc.view.setdefault("meta", {})["cost"] = rc.meter.snapshot()
            rc.checkpoint()
            run.finished = True
            if rc.view["status"] == "stopped":
                rc.queue.put_nowait({"type": "cost", "calls": rc.meter.calls, "usd": round(rc.meter.usd, 6)})
            rc.queue.put_nowait(None)
            asyncio.get_running_loop().call_later(120, lambda: self.runs.pop(run.rc.run_id, None))

    def stop(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if not run or run.finished or not run.task:
            return False
        run.task.cancel()
        return True


manager = RunManager()


def house_ctx(rc: RunContext) -> CallContext:
    return CallContext(meter=rc.house, chat_id=rc.chat_id, run_id=rc.run_id, on_event=rc.ctx.on_event)


async def context_event(rc: RunContext, model_id: str) -> dict:
    m = await memory.meter(rc.chat_id, model_id)
    await rc.emit({"type": "context", **m})
    return m


def compact_note(res: memory.CompactResult) -> str:
    if not res.ok:
        return f"Could not summarize: {res.reason}"
    extra = f", {res.preserved_extra} exact details re-attached" if res.preserved_extra else ""
    return (f"Older messages summarized ({res.summarized} messages, {res.ledger_edits} facts saved to the ledger{extra}). "
            "Nothing deleted; every message is still searchable.")


async def do_compact(rc: RunContext, model_id: str) -> bool:
    """Auto-compact like Claude: shows the four checked steps, never deletes anything (spec Part 2 section 7)."""
    async def progress(step: int):
        await rc.emit({"type": "compact", "step": step, "done": step >= 4})

    await rc.status("Summarizing older messages safely")
    res = await memory.compact(rc.chat_id, model_id, house_ctx(rc), progress)
    text = compact_note(res)
    memory.add_message(rc.chat_id, "sys", text)
    await rc.emit({"type": "note", "text": text})
    await context_event(rc, model_id)
    return res.ok


async def pipeline(rc: RunContext, text: str, model_id: str) -> Result:
    """Stages 2 to 4 (the gateway ran already)."""
    req = rc.req
    preliminary = await estimate.estimate(req, rc.chat_id)
    if preliminary["usd"] > rc.meter.remaining:
        question = (f"This question is estimated at {usd(preliminary['usd'])}, above the approved {usd(rc.meter.budget)} cap. "
                    "Use fewer agents or rounds, pick a cheaper model, or approve a higher one-question limit before sending.")
        await rc.warn(question)
        await rc.emit({"type": "clarify", "question": question})
        return Result(question, partial=True)
    m = await memory.meter(rc.chat_id, model_id)
    if m["percent"] >= config.LEVEL_COMPACT:   # C37 / C38: compact before sending if it will not fit
        if rc.settings["autoCompact"]:
            if not await do_compact(rc, model_id):
                return Result("This context cannot fit safely. Shorten the message, choose a larger-window model, or start a new chat with summary.", warning="No history was silently removed.", partial=True)
        else:
            await rc.emit({"type": "context", **m})
            return Result("The chat is almost full. Summarize it, start a new chat with summary, or download it before continuing.", warning="Automatic summarizing is off; no new answer was requested.", partial=True)

    # Any earlier answer makes this a follow-up, however short the chat is (a token threshold missed young chats).
    has_history = bool(db.one("SELECT 1 FROM messages WHERE chat_id=? AND role='assistant' AND content<>'' LIMIT 1", (rc.chat_id,)))
    r = await router.route(text, req["mode"], has_history=has_history, has_files=bool(files.chat_readings(rc.chat_id)), ctx=rc.ctx)
    await rc.emit({"type": "route", "kind": r.kind, "reason": r.reason if req["mode"] == "auto" else ""})
    if r.refusal:
        req["refused"] = True
        return Result(r.refusal)
    if r.clarify:   # C2
        await rc.emit({"type": "clarify", "question": r.clarify})
        await rc.text(r.clarify)
        return Result(r.clarify)
    est = await estimate.estimate({**req, "mode": r.kind}, rc.chat_id)
    if est["usd"] > rc.meter.remaining:
        return Result(f"The selected mode may cost {usd(est['usd'])}, above the remaining {usd(rc.meter.remaining)}. Pick fewer agents/rounds or a cheaper model.", warning="The mode did not run beyond the approved budget.", partial=True)

    # A mixed team must fit its smallest model, not the hidden Simple setting.
    models = [req["simple"]["model"]]
    if r.kind == "thinker" or (r.kind == "planner" and req["runIn"] != "simple"):
        models = ([req["team"]["model"]] if req["team"].get("source") == "same" else req["team"].get("mixed", [])) or models
        if req["team"].get("composer", "auto") != "auto":
            models.append(req["team"]["composer"])
    model_id = min(models, key=lambda mid: registry.get(mid).context)
    rc.req["contextModel"] = model_id
    if model_id != req["simple"]["model"] and (await memory.meter(rc.chat_id, model_id))["percent"] >= config.LEVEL_COMPACT:
        if not rc.settings["autoCompact"] or not await do_compact(rc, model_id):
            return Result("The selected team's smaller context window does not fit. Summarize or use larger-window models first.")

    async with asyncio.timeout(max(1.0, rc.remaining_time())):
        if r.kind == "thinker":
            return await run_thinker(rc, text)
        if r.kind == "planner":
            return await run_planner(rc, text)
        return await run_simple(rc, text)


def _friendly(e: LLMError) -> str:
    s = safe_message(e)
    if "credits" in s.lower():
        return "The model provider is out of credits. Add credits or pick a different provider."
    if "401" in s or "API key" in s:
        return "The model provider rejected the API key. Check the key in .env."
    return f"The model call failed after retries and fallbacks: {s}"


async def execute(rc: RunContext) -> None:
    req, chat_id, ai_id = rc.req, rc.chat_id, rc.req["id"]
    text, model_id = req["prompt"], req["simple"]["model"]
    stopped, result = False, None
    try:
        memory.ensure_chat(chat_id)
        if not req.get("retryOf"):
            memory.add_message(chat_id, "user", text, meta={"files": req.get("files", [])})
        memory.add_message(chat_id, "assistant", "", model=model_id, mid=ai_id, meta={"view": rc.view})

        ok, refusal = gateway.check_input(text)   # stage 1 (C1)
        if not ok:
            req["refused"] = True
            await rc.emit({"type": "route", "kind": "simple", "reason": ""})
            await rc.text(refusal)
            result = Result(refusal)
        else:
            async with asyncio.timeout(max(0.1, rc.remaining_time())):
                result = await pipeline(rc, text, model_id)
    except asyncio.CancelledError:
        stopped = True
        rc.view["status"] = "stopped"
        result = Result(rc.partial_text("you pressed Stop"), partial=True)
    except BudgetExceeded as e:   # C20: stop at the budget, keep progress
        await rc.warn(f"Stopped at the budget ({usd(e.budget)}). What was done is kept.")
        result = Result(rc.partial_text("the question budget was reached"), partial=True)
    except TimeoutError:
        await rc.warn("Stopped at the time limit. What was done is kept.")
        result = Result(rc.partial_text("the time limit was reached"), partial=True)
    except LLMError as e:
        await rc.emit({"type": "error", "message": _friendly(e)})
    except Exception as e:
        if isinstance(e, getattr(memory, "ContextOverflow", ())):
            message = "The complete context does not fit. Summarize, start a new chat with summary, or choose a larger model."
            await rc.emit({"type": "clarify", "question": message})
            result = Result(message, warning="No messages were silently dropped.")
        else:
            log.exception("run failed")
            await rc.emit({"type": "error", "message": "Internal error. The details are in the server log."})

    # stage 5: final check, save, remember, finish
    final_text = (result.text if result else rc.view["text"]) or rc.view["text"]
    if result and not stopped and rc.view["status"] != "error":
        final_text, _notes = output.final_check(final_text)   # C21
        if final_text != rc.view["text"]:
            await rc.text(final_text, replace=True)
        if result.warning:
            await rc.warn(result.warning)   # C19
    rc.view["text"] = final_text
    rc.view.setdefault("meta", {}).update({"cost": rc.meter.snapshot(), "model": result.model if result else model_id})
    rc.checkpoint()
    if stopped:
        rc.view["costUsd"], rc.view["calls"] = round(rc.meter.usd, 6), rc.meter.calls
        rc.checkpoint()
        return
    if rc.view["status"] == "error":
        await rc.cost()
        rc.checkpoint()
        return
    try:
        if (await context_event(rc, req.get("contextModel", model_id)))["percent"] >= config.LEVEL_COMPACT and rc.settings["autoCompact"] and not req.get("refused") and rc.remaining_time() > 0:
            async with asyncio.timeout(rc.remaining_time()):
                await do_compact(rc, req.get("contextModel", model_id))
    except BudgetExceeded:
        await rc.warn("The answer is saved. Automatic summarizing was skipped because it would exceed this question's budget.")
    except TimeoutError:
        await rc.warn("The answer is saved. Automatic summarizing stopped at the time limit.")
    except Exception:
        log.exception("post-run context check failed")
    if not req.get("refused") and (not result or not result.partial) and rc.remaining_time() > 0:
        # Text is already delivered; finalize after post-reply writes so their cost is visible.
        await _remember(rc, text, final_text)
    await rc.cost()
    if rc.meter.snapshot().get("estimatedCalls"):
        await rc.warn("Some provider usage was unavailable. The displayed total includes conservative estimated charges.")
    rc.view.setdefault("meta", {})["cost"] = rc.meter.snapshot()
    await rc.emit({"type": "done", "monthUsd": round(usage.month_spent(), 6)})
    rc.checkpoint()


async def _remember(rc: RunContext, user_text: str, answer: str) -> None:
    """Memory Writer: runs after the reply, off the critical path."""
    try:
        async with asyncio.timeout(max(0.1, min(30, rc.remaining_time()))):
            await memory.write_turn_memory(rc.chat_id, user_text, answer, house_ctx(rc))
            if hasattr(memory, "idle_cleanup"):
                memory.idle_cleanup()
    except BudgetExceeded:
        await rc.warn("The answer is saved. Memory updates stopped at this question's budget.")
    except TimeoutError:
        await rc.warn("The answer is saved. The memory update reached its time limit.")
    except Exception:
        log.warning("memory writer failed", exc_info=True)
