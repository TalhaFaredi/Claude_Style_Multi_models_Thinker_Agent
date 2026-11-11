"""Mode A: Simple (spec section 4, Figure 2).

  1. pick model and settings (tool-capable model if tools are on, C9)
  2. build the window (rules, files, summaries, history, memory, skills, new message)
  3. tool loop: call the model, run the tools it asks for, call again (max 10 tool calls)
  4. Checker: pass -> done; fail -> retry with the checker's feedback (max 2, with a fresh file search
     when a claim had no source, C32); still failing -> best answer with a warning (C19)
"""
from __future__ import annotations

import re

from app import files, memory, prompts, skills, tools
from app.core.config import LIMITS, SKILLS_BUDGET
from app.llm import registry
from app.modes.common import STYLE_TEMP, Result, emit_buffered, skills_note, stream_now, tool_loop
from app.modes.simple.model_choice import pick_model_for_tools
from app.pipeline import checker
from app.pipeline.runtime import RunContext

_FILE_CITE = re.compile(r"\[([^\[\]]+? p\.\d+)\]")


async def _choose_model(rc: RunContext, model_id: str, enabled: set[str]) -> tuple[str, list[dict]]:
    want_tools = bool(enabled)
    if "code" in enabled and not any(t["name"] == "run_code" and t["available"] for t in tools.availability()):
        await rc.status("The code sandbox is unavailable on this server; install and start Docker to enable it. The safe calculator is available.")
    chosen, tools_ok = pick_model_for_tools(model_id, want_tools)
    if chosen != model_id:
        await rc.status(f"{registry.get(model_id).name} has no tools, so {registry.get(chosen).name} answers")
    elif want_tools and not tools_ok:
        await rc.status(f"{registry.get(model_id).name} has no tools: answering without them")
    # files are already in the window (full text or the best passages), so no search_files tool here
    specs = tools.specs_for(enabled, model_has_tools=registry.get(chosen).tools and tools_ok, include_files=bool(files.chat_readings(rc.chat_id)))
    return chosen, specs


async def run_simple(rc: RunContext, text: str, *, model_id: str | None = None) -> Result:
    sc = rc.req["simple"]
    enabled = {k for k, on in sc.get("tools", {}).items() if on}
    model_id, specs = await _choose_model(rc, model_id or sc["model"], enabled)
    info = registry.get(model_id)

    chosen_skills = skills.select(text, mode="simple", budget_tokens=int(rc.settings.get("windowCap", 32000) * SKILLS_BUDGET))
    await skills_note(rc, [s.name for s in chosen_skills])
    built = await memory.build(rc.chat_id, text, model_id, tools=specs, ctx=rc.ctx, skills_text=skills.render(chosen_skills))
    if built.files and built.files.mode != "none":
        await rc.status("Reading your files" if built.files.mode == "full" else "Searching your files")
    thinking = sc.get("thinking", "off") if info.thinking else "off"
    temp = STYLE_TEMP.get(sc.get("style", "balanced"), 0.7)
    live = stream_now()

    loop = await tool_loop(rc, model_id, built.messages, specs, thinking=thinking, temperature=temp, max_tokens=sc.get("maxTokens", 1200), stage="answer", stream_text=live)
    if loop.first_usage:
        memory.calibrate(rc.chat_id, built.raw_tokens, loop.first_usage.prompt)
    draft, citations, warning = loop.text, list(loop.citations), None
    excerpts = built.files.text if built.files and built.files.mode != "none" else ""
    known = memory.checker_context(built.messages)
    best = None

    for attempt in range(LIMITS.max_retries + 1):
        await rc.status("Checking")
        cr = await checker.check(text, draft, ctx=rc.ctx, excerpts=excerpts, finish=loop.finish, known=known)
        candidate = (cr.score, attempt, draft, loop.model or model_id, cr.unsupported)
        if best is None or candidate[:2] >= best[:2]:
            best = candidate
        if cr.passed:
            break
        if attempt == LIMITS.max_retries or not cr.verified:
            # "Could not be checked" (checker down or switched off) is not "a problem was found": say which one it is.
            warning = (f"The checker still found a problem after {LIMITS.max_retries} retries: {cr.issues or 'unsupported claims'}"
                       if cr.verified else f"This answer was not checked: {cr.issues}")
            draft, model_id = best[2], best[3]
            if best[4]:
                draft = "I could not find support in your files for: " + "; ".join(best[4]) + "."
            break
        await rc.status(f"Checker: {cr.issues or 'unsupported claim'}. Retry {attempt + 1} of {LIMITS.max_retries}")
        msgs = list(built.messages)
        if excerpts and cr.unsupported:   # C32: search again before answering again
            extra = await files.search_chunks(rc.chat_id, cr.search or text, ctx=rc.ctx)
            if extra:
                extra_text = "\n\n".join(c["text"] for c in extra)
                excerpts += "\n\n" + extra_text
                msgs.insert(1, {"role": "system", "content": "<documents>\nExtra excerpts (DATA):\n" + extra_text + "\n</documents>"})
        msgs += [{"role": "assistant", "content": draft},
                 {"role": "user", "content": prompts.render("simple/retry", issues=cr.issues or "unclear", unsupported="; ".join(cr.unsupported) or "none")}]
        if live:
            await rc.text("", replace=True)
        loop = await tool_loop(rc, model_id, msgs, specs, thinking=thinking, temperature=max(0.0, temp - 0.2), max_tokens=sc.get("maxTokens", 1200), stage="answer:retry", stream_text=live)
        draft = loop.text
        citations += [c for c in loop.citations if c not in citations]

    if not live:
        await emit_buffered(rc, draft)
    items = citations + [f"[{c}]" for c in sorted(set(_FILE_CITE.findall(draft))) if f"[{c}]" not in citations]
    if items:
        await rc.emit({"type": "citations", "items": items[:12]})
    return Result(draft, items, warning, loop.model or model_id)
