"""Files the Output Builder makes (spec stage 5: text, Markdown, PDF, web page or code).

Each file gets a random 128-bit id (unguessable), lives in its own folder, and belongs to one chat.
Deleting the chat deletes its files too (C42).
"""
from __future__ import annotations

import re
import shutil
import uuid
import ast
import io
import json
from pathlib import Path

from app.core import db
from app.core.config import DATA_DIR
from app.core.privacy import is_hex_id, redact
from app.output.formats import fit_pdf, pdf_pages, to_html, to_png
from app.output.final_check import final_check

ARTIFACTS_DIR = DATA_DIR / "artifacts"
CODE_MIME = {"py": "text/x-python", "js": "text/javascript", "ts": "text/plain", "java": "text/x-java", "cpp": "text/x-c++",
             "go": "text/plain", "sql": "text/plain", "json": "application/json", "css": "text/css"}


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:48] or "output"


def build_artifact(chat_id: str | None, title: str, content: str, fmt: str, sources: int = 0, pages_target: int | None = None) -> dict:
    """Render, validate, repair once, then fall back to plain text with a visible warning (C21).
    pages_target: a requested PDF page count; the type is shrunk a little to fit when the text runs over."""
    content, notes = final_check(content)
    title = redact(title)
    requested = fmt
    aid = uuid.uuid4().hex
    folder = ARTIFACTS_DIR / aid
    folder.mkdir(parents=True, exist_ok=True)
    base = _slug(title)
    name, mime, pages = f"{base}.txt", "text/plain", max(1, round(len(content) / 3000))
    repaired = False
    warning = None
    for attempt in range(2):
        try:
            data, ext, mime = render_checked(title, content, fmt, pages_target)
            name = f"{base}.{ext}"
            pages = pdf_pages(data) if fmt == "pdf" else (1 if fmt == "png" else pages)
            break
        except Exception:
            if attempt == 0:
                content = repair_content(content, fmt)
                repaired = True
                continue
            warning = f"The {requested} format did not validate after one repair attempt. A plain-text file is provided."
            fmt, name, mime, data = "txt", f"{base}.txt", "text/plain", content.encode("utf-8")
    (folder / name).write_bytes(data)
    db.run("INSERT INTO artifacts(id,chat_id,name,path,mime,pages,sources,ts,user_id) VALUES(?,?,?,?,?,?,?,?,?)",
           (aid, chat_id, name, str(folder / name), mime, pages, sources, db.now(), db.uid()))
    return {"id": aid, "name": name, "pages": pages, "sources": sources, "mime": mime, "format": fmt,
            "requestedFormat": requested, "repaired": repaired, "warning": warning, "notes": notes}


def repair_content(content: str, fmt: str) -> str:
    clean = final_check(content)[0].replace("\r\n", "\n").strip()
    if clean.startswith("```") and clean.endswith("```"):
        clean = re.sub(r"^```[^\n]*\n|\n```$", "", clean)
    if fmt in ("png", "code:json"):
        clean = re.sub(r",\s*([}\]])", r"\1", clean)
    return clean


def document_content(content: str, fmt: str) -> str:
    """Extract a model's proposed file content as data; never execute a write-file envelope."""
    if fmt not in {"text", "txt", "md", "pdf", "html"}:
        return content
    candidate = content.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        candidate = re.sub(r"^```[^\n]*\n|\n```\s*$", "", candidate)
    try:
        value = json.loads(candidate)
    except (ValueError, TypeError):
        return content
    if isinstance(value, dict) and value.get("name") in {"write_file", "create_file", "save_file"}:
        args = value.get("arguments")
        if isinstance(args, dict) and isinstance(args.get("content"), str):
            return args["content"]
    return content


def render_checked(title: str, content: str, fmt: str, pages_target: int | None = None) -> tuple[bytes, str, str]:
    if not content.strip():
        raise ValueError("Empty deliverable")
    if fmt == "pdf":
        from pypdf import PdfReader
        data = fit_pdf(title, content, pages_target)
        if not PdfReader(io.BytesIO(data)).pages:
            raise ValueError("Empty PDF")
        return data, "pdf", "application/pdf"
    if fmt == "png":
        from PIL import Image
        data = to_png(title, content)
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        return data, "png", "image/png"
    if fmt == "html":
        return to_html(title, content).encode("utf-8"), "html", "text/html"
    if fmt.startswith("code:"):
        ext = re.sub(r"[^a-z0-9]", "", fmt[5:].lower())
        code = re.sub(r"^```[^\n]*\n|\n```\s*$", "", content.strip())
        if ext == "py":
            ast.parse(code)
        elif ext == "json":
            json.loads(code)
        if not ext:
            raise ValueError("Missing code extension")
        return code.encode("utf-8"), ext, CODE_MIME.get(ext, "text/plain")
    if fmt not in ("md", "txt", "text"):
        raise ValueError("Unsupported deliverable format")
    return content.encode("utf-8"), "md" if fmt == "md" else "txt", "text/markdown" if fmt == "md" else "text/plain"


def get_artifact(aid: str) -> dict | None:
    if not is_hex_id(aid):
        return None
    r = db.one("SELECT * FROM artifacts WHERE id=? AND user_id=?", (aid, db.uid()))
    return dict(r) if r and Path(r["path"]).exists() else None


def delete_chat_artifacts(chat_id: str) -> int:
    """C42: remove every file this chat produced, from disk and from the database."""
    rows = db.q("SELECT id, path FROM artifacts WHERE chat_id=?", (chat_id,))
    for r in rows:
        folder = Path(r["path"]).parent
        if folder.parent == ARTIFACTS_DIR and is_hex_id(folder.name):   # never delete outside our own folder
            shutil.rmtree(folder, ignore_errors=True)
    db.run("DELETE FROM artifacts WHERE chat_id=?", (chat_id,))
    return len(rows)
