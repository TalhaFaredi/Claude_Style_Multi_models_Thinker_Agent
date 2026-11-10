"""Document Card: title, pages, summary, outline with page numbers, tables and charts. The cards of all files
in a chat stay in the window, so the model never forgets a file exists (spec Part 2 section 3)."""
from __future__ import annotations

import re
from pathlib import Path

from app import llm, prompts
from app.core import config

_HEADING = re.compile(r"^(?:#{1,3}\s+.+|\d+(?:\.\d+)*[.)]?\s+[A-Z].{2,70}|[A-Z][A-Z0-9 ,&:\-]{3,60})$")


def find_headings(text: str) -> list[str]:
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if 3 < len(s) <= 80 and _HEADING.match(s) and not s.endswith((".", ",")):
            out.append(s.lstrip("# ").strip())
    return out


async def make_card(name: str, pages: list[dict], ctx: llm.CallContext, paid: bool = False) -> dict:
    outline = [{"title": h, "page": p["page"]} for p in pages for h in find_headings(p["text"])[:6]]
    head = "\n\n".join(p["text"] for p in pages if p["text"])[:20000]
    summary = ""
    if head.strip() and paid:
        try:
            res = await llm.complete(config.WRITER_MODEL, [
                {"role": "system", "content": prompts.render("files/card")},
                {"role": "user", "content": f"<document name=\"{name}\">\n{head}\n</document>"}],
                stage="file:card", ctx=ctx, temperature=0.2, max_tokens=300)
            summary = res.text.strip()
        except Exception:
            summary = head[:300].replace("\n", " ")
    elif head.strip():
        summary = " ".join(re.split(r"(?<=[.!?])\s+", head.strip())[:3])[:600]
    return {
        "title": next((h["title"] for h in outline), Path(name).stem), "pages": len(pages), "summary": summary, "outline": outline[:40],
        "tables": [p["page"] for p in pages if p["table"]],
        "charts": [{"page": p["page"], "description": p["text"].split("[Chart description]")[-1].strip()[:300]}
                   for p in pages if p["kind"] == "chart" and "[Chart description]" in p["text"]],
        "weakPages": [p["page"] for p in pages if p["weak"]],
    }


def cards_text(readings: list[dict]) -> str:
    """One line per file, for the window."""
    lines = []
    for r in readings:
        c = r["card"]
        outline = "; ".join(f"{o['title']} (p.{o['page']})" for o in c.get("outline", [])[:8])
        lines.append(f"- {r['name']}: {c.get('pages', '?')} pages. {c.get('summary', '')}" + (f" Outline: {outline}." if outline else "")
                     + (f" Tables on pages {c['tables'][:10]}." if c.get("tables") else "") + (f" Unreadable pages: {c['weakPages'][:10]}." if c.get("weakPages") else ""))
    return "\n".join(lines)
