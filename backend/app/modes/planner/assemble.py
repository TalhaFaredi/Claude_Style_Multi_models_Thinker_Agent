"""Step 5: write the final deliverable from the step results and hand it to the Output Builder."""
from __future__ import annotations

from app import llm, output, prompts, skills
from app.modes.common import Result
from app.modes.planner.plan import Step
from app.core.config import LIMITS
from app.pipeline import checker
from app.pipeline.runtime import RunContext

ASSEMBLE_MAX_TOKENS = 2500


def _form(fmt: str) -> str:
    if fmt.startswith("code:"):
        return prompts.render("planner/form_code")
    if fmt == "png":
        return prompts.render("planner/form_png")
    return prompts.render("planner/form_text" if fmt == "text" else "planner/form_document")


def _format_skill(fmt: str) -> str:
    """The skill that serves this output format (pdf-report for a PDF, web-page for html, ...)."""
    key = "code" if fmt.startswith("code:") else fmt
    return skills.render(skills.select("", mode="planner", fmt=key, limit=1, budget_tokens=600))


async def assemble(rc: RunContext, goal: str, steps: list[Step], meta: dict, sources: set[str]) -> Result:
    fmt = meta.get("final_format", "text")
    model = rc.req["simple"]["model"]
    material = "\n\n".join(f"## Step {i + 1}: {s.task}\n{s.result}" for i, s in enumerate(steps) if s.result)
    system = prompts.render("planner/assemble", form=_form(fmt))
    requested_pages = output.requested_pages(goal, fmt)
    if requested_pages:
        system +=f"\nThe PDF must contain exactly {requested_pages} pages. Put <!-- pagebreak --> on its own line between pages; include exactly {max(0, requested_pages - 1)} breaks. Keep each page short enough to avoid overflow."
    if skill_text := _format_skill(fmt):
        system += "\n\n" + skill_text
    messages = [{"role": "system", "content": system}, {"role": "user", "content": f"Goal: {goal}\n\nMaterial (DATA):\n{material}"}]
    prepared = next((s.artifact for s in reversed(steps) if s.status == "done" and s.artifact), None)
    best, warning, passed = None, None, False
    for attempt in range(LIMITS.max_retries + 1):
        if prepared and attempt == 0:
            doc, finish = prepared["content"], ""
        else:
            res = await llm.complete(model, messages, stage="plan:assemble", ctx=rc.ctx, temperature=0.3,
                                     max_tokens=max(ASSEMBLE_MAX_TOKENS, rc.req["simple"].get("maxTokens", 1200)), thinking="off")
            doc, _ = output.final_check(output.document_content(res.text.strip(), fmt))
            finish = res.finish
        await rc.status("Checking the complete final deliverable")
        cr = await checker.check(goal, doc, ctx=rc.ctx, excerpts=material, finish=finish,
                                 done_test=f"Complete requested {fmt} deliverable; satisfy all user constraints, sources and required length.")
        if requested_pages:
            try:
                # The same fitting the file builder uses: slightly smaller type before asking the model to cut text.
                actual_pages = prepared["pages"] if prepared and prepared["content"] == doc else output.pdf_pages(output.fit_pdf(meta.get("title", "output"), doc, requested_pages))
                if actual_pages != requested_pages:
                    advice = ("shorten the text by about " + str(round(100 * (1 - requested_pages / actual_pages))) + "% and keep only the most important points"
                              if actual_pages > requested_pages else "add content or page breaks")
                    cr = checker.CheckResult(False, f"The rendered PDF has {actual_pages} pages; exactly {requested_pages} are required: {advice}. Use explicit page breaks.")
            except Exception:
                cr = checker.CheckResult(False, "The requested PDF could not be rendered. Correct its document format.")
        await rc.cost()
        if best is None or cr.score >= best[0]:
            best = (cr.score, doc)
        if cr.passed:
            passed = True
            break
        if attempt == LIMITS.max_retries or not cr.verified:
            doc = best[1]
            warning = f"The final deliverable could not pass all checks: {cr.issues}"
            break
        messages += [{"role": "assistant", "content": doc}, {"role": "user", "content": f"Correct the final deliverable: {cr.issues}. Unsupported claims: {'; '.join(cr.unsupported) or 'none'}. Return the complete corrected deliverable."}]
    if fmt == "text":
        for i in range(0, len(doc), 40):
            await rc.text(doc[i:i + 40])
        return Result(doc, sorted(sources)[:12], warning, model)
    f = dict(prepared) if prepared and prepared["content"] == doc else output.build_artifact(rc.chat_id, meta.get("title", "output"), doc, fmt, sources=len(sources), pages_target=requested_pages)
    f["checked"] = passed and not f.get("warning")
    if f.get("warning"):
        warning = f["warning"]
        await rc.warn(warning)
    await rc.emit({"type": "output", "file": {"id": f["id"], "name": f["name"], "pages": f["pages"], "sources": f["sources"], "checked": f["checked"], "warning": warning}})
    done = sum(s.status == "done" for s in steps)
    retried = sum(1 for s in steps if s.retries)
    actual = f.get("format", fmt)
    kind = "web page" if actual == "html" else actual.split(":")[-1].upper()
    msg = f"The {kind} is ready: {f['name']}. {done} of {len(steps)} steps passed their checks" + (f"; {retried} needed a retry." if retried else ".")
    await rc.text(msg)
    return Result(msg, sorted(sources)[:12], warning, model, output=f)
