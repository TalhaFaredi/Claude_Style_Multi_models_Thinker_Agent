"""Step 3 and 4 of the attachment pipeline: check every page for free, then price the cheapest reader per page
(spec Part 2 Figure 6 and the 200-page worked example)."""
from __future__ import annotations

import re
import importlib.util
import math
from pathlib import Path

from app.core import config, db
from app.files.common import CHART_OUT_TOKENS, IMAGE_EXT, OCR_API_PER_PAGE, SCAN_OUT_TOKENS, VISION_PAGE_TOKENS, PageInfo
from app.files.readers import extract_text_pages, pdf_layout
from app.llm import registry


def looks_like_table(text: str) -> bool:
    rows = [ln for ln in text.splitlines() if ln.strip()]
    tabular = [ln for ln in rows if ln.count("|") >= 2 or ln.count("\t") >= 2 or len(re.findall(r"\S\s{3,}\S", ln)) >= 2]
    return len(tabular) >= 3 and len(tabular) >= 0.4 * len(rows)


def analyze(name: str, data: bytes) -> list[PageInfo]:
    """Text layer, scan, chart, table: decided per page without any paid call."""
    pages = []
    ext = Path(name).suffix.lower()
    layout = pdf_layout(data) if ext == ".pdf" else None
    for i, (text, n_img) in enumerate(extract_text_pages(name, data), start=1):
        chars = len(text.strip())
        if ext in IMAGE_EXT:
            kind = "scan"
        elif chars < 30:
            kind = "scan" if (n_img > 0 or ext == ".pdf") else "text"
        elif ext in (".docx", ".pptx", ".xlsx", ".xlsm") and n_img > 0:
            kind = "scan"
        elif (layout and layout[i - 1]["chart"]) or n_img > 0:
            kind = "chart"
        else:
            kind = "text"
        garbled = text.count("\ufffd") > max(3, chars * .05)
        if garbled:
            kind = "scan"
        pages.append(PageInfo(i, kind, chars, bool(layout and layout[i - 1]["table"]) or looks_like_table(text), n_img))
    return pages


def kinds_summary(pages: list[dict | PageInfo]) -> dict:
    ps = [p.to_dict() if isinstance(p, PageInfo) else p for p in pages]
    return {"text": sum(p["kind"] == "text" for p in ps), "scan": sum(p["kind"] == "scan" for p in ps),
            "chart": sum(p["kind"] == "chart" for p in ps), "tables": sum(bool(p.get("table")) for p in ps),
            "textChars": sum(p.get("chars", 0) for p in ps)}


def reader_availability() -> dict[str, dict]:
    v = registry.get(config.VISION_MODEL)
    vision_ok = v.available and v.vision
    local_ok = importlib.util.find_spec("rapidocr_onnxruntime") is not None
    api_ok = bool(config.OPENROUTER_KEY)
    return {
        "auto": {"available": True, "reason": ""},
        "text": {"available": True, "reason": ""},
        "local": {"available": local_ok, "reason": "" if local_ok else "Install the bundled rapidocr-onnxruntime dependency for local OCR"},
        "api": {"available": api_ok, "reason": "" if api_ok else "Set the OpenRouter API key to use the Mistral OCR parser"},
        "vision": {"available": vision_ok, "reason": "" if vision_ok else f"Vision model unavailable: {v.why_unavailable or 'no vision support'}"},
    }


def reading_plan(kinds: dict, reader: str) -> dict:
    """Per page type: which reader and what it costs. Text pages are always free."""
    vm = registry.get(config.VISION_MODEL)
    from app.llm.client import _maximum_cost
    per_page = {kind: _maximum_cost(vm, {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "page"}}]}],
                                         "max_tokens": output}) for kind, output in (("scan", SCAN_OUT_TOKENS), ("chart", CHART_OUT_TOKENS))}
    rows = [{"label": f"{kinds['text']} normal pages", "kind": "text", "count": kinds["text"], "reader": "Free text reading", "cost": 0.0}]
    for kind in ("scan", "chart"):
        n = kinds[kind]
        if not n:
            continue
        label = f"{n} scanned pages" if kind == "scan" else f"{n} chart pages"
        if kind == "chart" and not db.get_setting("chartDescriptions", True):
            rows.append({"label": label, "kind": kind, "count": n, "reader": "Chart descriptions are off; labels only", "cost": 0.0})
            continue
        if reader == "text":
            rows.append({"label": label, "kind": kind, "count": n, "reader": "Cannot be read with Text only", "cost": 0.0})
        elif reader in ("auto", "vision"):
            local = kind == "scan" and reader == "auto" and reader_availability()["local"]["available"]
            rows.append({"label": label, "kind": kind, "count": n, "reader": "Local OCR (free)" if local else f"Vision model maximum ({vm.name}); actual usage billed", "cost": 0.0 if local else math.ceil(n * per_page[kind] * 1e6) / 1e6,
                         "expectedCost": 0.0 if local else vm.call_cost(n*VISION_PAGE_TOKENS, n*(SCAN_OUT_TOKENS if kind == "scan" else CHART_OUT_TOKENS))})
        elif reader == "local":
            rows.append({"label": label, "kind": kind, "count": n, "reader": f"Vision chart reader ({vm.name})" if kind == "chart" else "Local OCR (free)", "cost": round(n*per_page[kind],6) if kind == "chart" else 0.0})
        else:
            from app.files.ocr import api_page_cost
            price = per_page[kind] if kind == "chart" else api_page_cost()
            rows.append({"label": label, "kind": kind, "count": n, "reader": "Vision chart reader" if kind == "chart" else "Mistral OCR API", "cost": round(n * price, 6)})
    if reader not in ("text", "local") and db.get_setting("embeddings", True) and sum(kinds[k] for k in ("text", "scan", "chart")):
        from app.files.search import embedding_cost
        tokens = kinds.get("textChars", 0) * 4 + kinds["scan"] * SCAN_OUT_TOKENS * 8 + kinds["chart"] * CHART_OUT_TOKENS * 8
        tokens += sum(kinds[k] for k in ("text", "scan", "chart")) * 400 + 64
        from app.files.common import FileError
        try:
            price = embedding_cost(tokens)
            reason = config.EMBED_MODEL
        except FileError as error:
            price, reason = 0.0, f"Meaning search disabled: {error}"
        rows.append({"label": "Meaning search index (maximum)", "kind": "index", "count": 1, "reader": reason,
                     "cost": round(price, 6)})
    return {"rows": rows, "total": round(sum(r["cost"] for r in rows), 6)}
