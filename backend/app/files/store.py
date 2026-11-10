"""Attachment pipeline, steps 1 to 5 (spec Part 2 Figure 6):

  upload -> SHA-256 fingerprint -> free page check -> cheapest reader per page (paid only after the
  cost check) -> Document Card + chunks + index -> Parse Cache (fingerprint + reader + version)

A file read before with the same reader costs $0 (C22). A chat can only read files attached to it, and
deleting the last chat that uses a file removes the file, its readings, chunks, indexes and page images.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from app import llm
from app.core import config, db
from app.core.config import DATA_DIR, PARSE_VERSION
from app.core.costmeter import CostMeter
from app.core.privacy import is_fingerprint
from app.files.analysis import analyze, kinds_summary, reader_availability, reading_plan
from app.files.card import make_card
from app.files.common import READER_IDS, FileError, fingerprint
from app.files.readers import extract_text_pages
from app.files.search import index_chunks
from app.files.vision import page_image, read_page

FILES_DIR = DATA_DIR / "files"
PAGES_DIR = DATA_DIR / "pages"


def is_linked(chat_id: str, fp: str) -> bool:
    return db.one("SELECT 1 FROM file_chats WHERE chat_id=? AND fingerprint=?", (chat_id, fp)) is not None


def chat_fingerprints(chat_id: str) -> list[str]:
    return [r["fingerprint"] for r in db.q("SELECT fingerprint FROM file_chats WHERE chat_id=? ORDER BY ts", (chat_id,))]


def link(chat_id: str, fp: str, reader: str | None = None) -> None:
    db.run("INSERT OR IGNORE INTO file_chats(chat_id,fingerprint,ts,reader) VALUES(?,?,?,?)", (chat_id, fp, db.now(), reader))
    if reader:
        db.run("UPDATE file_chats SET reader=? WHERE chat_id=? AND fingerprint=?", (reader, chat_id, fp))


def store_original(fp: str, name: str, data: bytes) -> Path:
    folder = FILES_DIR / fp[:2]
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (fp + Path(name).suffix.lower())
    target.write_bytes(data)
    return target


def ingest(chat_id: str, name: str, data: bytes) -> dict:
    """Store the file, fingerprint it, attach it to the chat, and return the free page check."""
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise FileError("File is larger than 25 MB", 413)
    if not data:
        raise FileError("File is empty", 422)
    fp = fingerprint(data)
    if db.one("SELECT 1 FROM files WHERE fingerprint=?", (fp,)) is None:
        pages = analyze(name, data)
        target = store_original(fp, name, data)
        db.run("INSERT INTO files(fingerprint,name,size,mime,pages,kinds,path,created) VALUES(?,?,?,?,?,?,?,?)",
               (fp, Path(name).name[:200], len(data), "", len(pages), json.dumps({"pages": [p.to_dict() for p in pages]}), str(target), db.now()))
    link(chat_id, fp)
    return file_status(fp)


def file_status(fp: str) -> dict:
    row = db.one("SELECT * FROM files WHERE fingerprint=?", (fp,))
    if row is None:
        raise FileError("Unknown file", 404)
    kinds = kinds_summary(json.loads(row["kinds"])["pages"])
    read = {}
    for r in db.q("SELECT reader,cost,pages FROM readings WHERE fingerprint=? AND version=?", (fp, PARSE_VERSION)):
        ready = [p["page"] for p in json.loads(r["pages"]) if not p.get("pending")]
        read[r["reader"]] = {"cost": r["cost"], "pagesRead": ready, "complete": len(ready) == row["pages"]}
    return {"fingerprint": fp, "name": row["name"], "size": row["size"], "pages": row["pages"], "kinds": kinds,
            "plans": {rid: reading_plan(kinds, rid) for rid in READER_IDS}, "readers": reader_availability(), "readBefore": read,
            "pageDetails": json.loads(row["kinds"])["pages"]}


def reading_estimate(chat_id: str, fp: str, reader: str, text_only: bool = False, pages: list[int] | None = None) -> dict:
    if not is_linked(chat_id, fp) or reader not in READER_IDS:
        raise FileError("Unknown file or reader", 404)
    row = db.one("SELECT kinds FROM files WHERE fingerprint=?", (fp,))
    metadata = json.loads(row["kinds"])["pages"]
    wanted = set(pages) if pages is not None else {p["page"] for p in metadata}
    if not wanted or not wanted <= {p["page"] for p in metadata}:
        raise FileError("Choose valid page numbers (starting at 1)", 422)
    effective = "text" if text_only else reader
    cached = db.one("SELECT pages FROM readings WHERE fingerprint=? AND reader=? AND version=?", (fp, effective, PARSE_VERSION))
    ready = {p["page"] for p in json.loads(cached["pages"]) if not p.get("pending")} if cached else set()
    needed = wanted - ready
    plan = reading_plan(kinds_summary([p for p in metadata if p["page"] in needed]), effective)
    return {**plan, "pages": sorted(wanted), "cachedPages": sorted(wanted & ready), "pagesToRead": sorted(needed)}


async def _read_file(chat_id: str, fp: str, reader: str, text_only: bool = False, max_cost: float | None = None,
                     pages: list[int] | None = None) -> dict:
    """Read a file once. Returns the Document Card and the real cost ($0 when the reading is reused)."""
    if not is_fingerprint(fp) or not is_linked(chat_id, fp):
        raise FileError("Unknown file", 404)   # a chat can only read its own files
    row = db.one("SELECT * FROM files WHERE fingerprint=?", (fp,))
    if row is None:
        raise FileError("Unknown file", 404)
    if reader not in READER_IDS:
        raise FileError("Unknown reader", 422)
    effective = "text" if text_only else reader
    if not reader_availability()[effective]["available"]:
        raise FileError(reader_availability()[effective]["reason"], 503)

    cached = db.one("SELECT * FROM readings WHERE fingerprint=? AND reader=? AND version=?", (fp, effective, PARSE_VERSION))
    plan = reading_estimate(chat_id, fp, reader, text_only, pages)
    if cached and not plan["pagesToRead"]:
        link(chat_id, fp, effective)
        return {"fingerprint": fp, "name": row["name"], "reused": True, "cost": 0.0, "card": json.loads(cached["card"] or "{}"), "readerUsed": effective}

    pages_meta = json.loads(row["kinds"])["pages"]
    from app.memory.settings import get_settings
    settings = get_settings()
    approved = float(max_cost) if max_cost is not None else 0.0
    if plan["total"] > approved + 1e-9:
        raise FileError("Reading costs more than you approved", 402, {"estimate": plan["total"], "plan": plan})
    from app.core.usage import month_start
    spent = float(db.one("SELECT COALESCE(SUM(cost),0) AS n FROM calls WHERE ts>=? AND ok=1 AND (stage LIKE 'file:%' OR stage LIKE 'embed:%')", (month_start(),))["n"])
    if spent + plan["total"] > float(settings["monthBudget"]) + 1e-9:
        raise FileError("The monthly reading budget would be exceeded. Choose Text only or raise the monthly budget in Settings.", 402,
                        {"estimate": plan["total"], "monthSpent": spent, "monthBudget": settings["monthBudget"]})
    if effective != "text" and any(p["kind"] == "chart" for p in pages_meta) and settings["chartDescriptions"] and not reader_availability()["vision"]["available"]:
        raise FileError(reader_availability()["vision"]["reason"], 503)

    data = Path(row["path"]).read_bytes()
    texts = extract_text_pages(row["name"], data)
    meter = CostMeter(budget=approved)
    ctx = llm.CallContext(meter=meter, chat_id=chat_id, run_id=f"read:{fp[:8]}")
    sem = asyncio.Semaphore(4)
    needed = set(plan["pagesToRead"])
    cached_pages = {p["page"]: p for p in json.loads(cached["pages"])} if cached else {}
    out_pages = [dict(cached_pages[m["page"]]) if m["page"] in cached_pages and m["page"] not in needed else
                 {"page": m["page"], "kind": m["kind"], "table": m["table"], "text": texts[i][0].strip(),
                  "weak": m["page"] not in needed, "pending": m["page"] not in needed, "image": None}
                 for i, m in enumerate(pages_meta)]
    keep_images = bool(db.get_setting("keepPageImages", True))

    async def do_page(p: dict):
        if p["page"] not in needed:
            return
        p["pending"] = False
        if p["kind"] == "text":
            return
        if effective == "text":
            p["weak"] = True   # scans and charts cannot be read with Text only
            return
        if p["kind"] == "chart" and not settings["chartDescriptions"]:
            p["weak"] = True
            return
        img = page_image(data, row["name"], p["page"])
        if img is None:
            p["weak"] = True   # vector chart / no embedded image: keep whatever text exists
            return
        async with sem:
            try:   # C29: the retry happens inside llm.complete(); then the page is marked weak
                from app.files.ocr import read_with_fallback
                got, used_reader = await read_with_fallback(img[0], img[1], p["kind"], effective, ctx)
                p["reader"] = used_reader
            except Exception as error:
                from app.core.costmeter import BudgetExceeded
                if isinstance(error, BudgetExceeded):
                    raise
                p["weak"] = True
                return
        if p["kind"] == "scan":
            office = Path(row["name"]).suffix.lower() in (".docx", ".pptx", ".xlsx", ".xlsm")
            p["text"] = ((p["text"] + "\n[Embedded picture text]\n") if office and p["text"] else "") + (got or p["text"])
        else:
            p["text"] = (p["text"] + "\n\n" if p["text"] else "") + f"[Chart description] {got}"
        if keep_images:
            folder = PAGES_DIR / fp[:16]
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{p['page']}.{img[1]}"
            target.write_bytes(img[0])
            p["image"] = str(target)

    await asyncio.gather(*(do_page(p) for p in out_pages))
    card = await make_card(row["name"], out_pages, ctx)
    cost = round(meter.usd, 6)
    card["cost"], card["readers"] = cost + (float(cached["cost"]) if cached else 0.0), sorted({p.get("reader", "text") for p in out_pages})
    with db.tx() as c:
        c.execute("INSERT OR REPLACE INTO readings(fingerprint,reader,version,pages,card,cost,ts) VALUES(?,?,?,?,?,?,?)",
                  (fp, effective, PARSE_VERSION, json.dumps(out_pages), json.dumps(card), cost, db.now()))
    await index_chunks(fp, effective, row["name"], out_pages, ctx=ctx, paid_embeddings=effective not in ("text", "local"))
    cost = round(meter.usd, 6)
    card["cost"] = cost + (float(cached["cost"]) if cached else 0.0)
    db.run("UPDATE readings SET card=?,cost=? WHERE fingerprint=? AND reader=? AND version=?", (json.dumps(card), card["cost"], fp, effective, PARSE_VERSION))
    link(chat_id, fp, effective)
    return {"fingerprint": fp, "name": row["name"], "reused": False, "cost": cost, "card": card, "readerUsed": effective}


_READ_LOCK = asyncio.Lock()


async def read_file(chat_id: str, fp: str, reader: str, text_only: bool = False, max_cost: float | None = None,
                    pages: list[int] | None = None) -> dict:
    """Serialize cache creation and monthly approval checks; pages within a reading still run in parallel."""
    from app.core.costmeter import BudgetExceeded
    async with _READ_LOCK:
        try:
            return await _read_file(chat_id, fp, reader, text_only, max_cost, pages)
        except BudgetExceeded as e:
            raise FileError("The approved reading budget was reached. No further paid page was started.", 402) from e


def detach(chat_id: str, fp: str) -> None:
    """Remove the file from one chat. Its reading stays in the Parse Cache while another chat uses it."""
    db.run("DELETE FROM file_chats WHERE chat_id=? AND fingerprint=?", (chat_id, fp))
    if not db.one("SELECT 1 FROM file_chats WHERE fingerprint=?", (fp,)):
        purge_file(fp)


def purge_file(fp: str) -> None:
    """Remove a file from every store, index and cache (C42): original, readings, chunks, search index, page images."""
    if not is_fingerprint(fp):
        return
    row = db.one("SELECT path FROM files WHERE fingerprint=?", (fp,))
    with db.tx() as c:
        c.execute("DELETE FROM chunk_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE fingerprint=?)", (fp,))
        c.execute("DELETE FROM chunks WHERE fingerprint=?", (fp,))
        c.execute("DELETE FROM readings WHERE fingerprint=?", (fp,))
        c.execute("DELETE FROM file_chats WHERE fingerprint=?", (fp,))
        c.execute("DELETE FROM files WHERE fingerprint=?", (fp,))
    if row and row["path"]:
        p = Path(row["path"])
        if p.parent.parent == FILES_DIR and p.name.startswith(fp):
            p.unlink(missing_ok=True)
    shutil.rmtree(PAGES_DIR / fp[:16], ignore_errors=True)


def forget_chat(chat_id: str) -> int:
    """Detach every file from a deleted chat; purge files no other chat uses. Returns files purged."""
    fps = [r["fingerprint"] for r in db.q("SELECT fingerprint FROM file_chats WHERE chat_id=?", (chat_id,))]
    db.run("DELETE FROM file_chats WHERE chat_id=?", (chat_id,))
    orphans = [fp for fp in fps if db.one("SELECT 1 FROM file_chats WHERE fingerprint=?", (fp,)) is None]
    for fp in orphans:
        purge_file(fp)
    return len(orphans)
