"""Chunks: pieces of up to 800 tokens cut at headings and paragraphs. A table is never cut mid-row; a long
table is split into groups of rows with the header row repeated. Every chunk starts with its file, section
and page (spec Part 2 section 3)."""
from __future__ import annotations

import re
from pathlib import Path

from app.core.config import CHUNK_TOKENS
from app.core.tokens import estimate_tokens
from app.files.card import find_headings


def chunk_pages(name: str, pages: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    section = Path(name).stem

    def emit(page: int, body: str, kind: str):
        if body.strip():
            chunks.append({"page": page, "section": section, "kind": kind, "text": f"[{name} | {section} | p.{page}]\n{body.strip()}"})

    for p in pages:
        text = p["text"]
        if not text.strip():
            continue
        kind = "chart" if p["kind"] == "chart" else "table" if p["table"] else "text"
        if p["table"]:
            rows = [r for r in text.splitlines() if r.strip()]
            header, group = rows[0], []
            for r in rows[1:] or [""]:
                if estimate_tokens("\n".join([header, *group, r])) > CHUNK_TOKENS and group:
                    emit(p["page"], "\n".join([header, *group]), kind)
                    group = []
                group.append(r)
            emit(p["page"], "\n".join([header, *group]), kind)
            continue
        cur = ""
        for para in re.split(r"\n\s*\n", text):
            hs = find_headings(para.split("\n")[0]) if para.strip() else []
            if hs:
                if cur:
                    emit(p["page"], cur, kind)
                    cur = ""
                section = hs[0][:70]
            if estimate_tokens(cur + para) > CHUNK_TOKENS and cur:
                emit(p["page"], cur, kind)
                cur = ""
            while estimate_tokens(para) > CHUNK_TOKENS:   # one huge paragraph
                cut = int(CHUNK_TOKENS * 3.8)
                emit(p["page"], para[:cut], kind)
                para = para[cut:]
            cur += para + "\n\n"
        emit(p["page"], cur, kind)
    return chunks
