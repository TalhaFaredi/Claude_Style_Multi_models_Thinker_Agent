"""Chats: list, open, rename, delete, context meter, ledger, Summarize now, export and import."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response

from app import files, memory
from app.api.common import defaults, sse
from app.api.schemas import ChatCreate, ChatPatch, CompactRequest
from app.core import usage
from app.core.config import MAX_IMPORT_BYTES
from app.core.costmeter import CostMeter
from app.llm import CallContext
from app.memory import portability
from app.pipeline.engine import compact_note

router = APIRouter()
log = logging.getLogger("api.chats")


def _chat_or_404(chat_id: str) -> dict:
    chat = memory.get_chat(chat_id)
    if not chat:
        raise HTTPException(404, "Unknown chat")
    return chat


def chat_files(chat_id: str) -> list[dict]:
    """The file chips of a chat: name, pages, ready, Document Card, reading cost."""
    readings = {r["fingerprint"]: r["card"] for r in files.chat_readings(chat_id)}
    out = []
    for fp in files.chat_fingerprints(chat_id):
        st, card = files.file_status(fp), readings.get(fp)
        out.append({"fingerprint": fp, "name": st["name"], "pages": st["pages"], "ready": card is not None, "card": card,
                    "cost": (card or {}).get("cost", 0.0)})
    return out


@router.get("/api/chats")
async def chats(q: str = ""):
    return memory.list_chats(q[:200])


@router.post("/api/chats")
async def new_chat(body: ChatCreate):
    return memory.create_chat(body.title, temp=body.temp or bool(memory.get_settings()["tempChat"]))


@router.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str, model: str | None = None):
    chat = _chat_or_404(chat_id)
    return {"chat": {"id": chat["id"], "title": chat["title"], "temp": bool(chat["temp"])}, "messages": memory.ui_messages(chat_id),
            "context": await memory.meter(chat_id, model or defaults()["simple"]["model"]), "files": chat_files(chat_id),
            "costUsd": round(usage.chat_cost(chat_id), 6)}


@router.patch("/api/chats/{chat_id}")
async def patch_chat(chat_id: str, body: ChatPatch):
    _chat_or_404(chat_id)
    if body.title is not None:
        memory.rename_chat(chat_id, body.title)
    return {"ok": True}


@router.delete("/api/chats/{chat_id}")
async def remove_chat(chat_id: str, deleteMemories: bool = False):
    _chat_or_404(chat_id)
    return memory.delete_chat(chat_id, deleteMemories)


@router.get("/api/chats/{chat_id}/context")
async def chat_context(chat_id: str, model: str):
    memory.ensure_chat(chat_id)
    return await memory.meter(chat_id, model)


@router.get("/api/chats/{chat_id}/ledger")
async def chat_ledger(chat_id: str):
    _chat_or_404(chat_id)
    return {"ledger": memory.ledger_items(chat_id), "summaries": memory.active_summaries(chat_id)}


@router.post("/api/chats/{chat_id}/compact")
async def compact_chat(chat_id: str, body: CompactRequest):
    """Summarize now (the Summarize button). Streams the four checked steps, then the result."""
    memory.ensure_chat(chat_id)
    usage.ensure_can_spend()
    q: asyncio.Queue = asyncio.Queue()

    async def work():
        ctx = CallContext(meter=CostMeter(budget=usage.limit_budget(body.maxCost)), chat_id=chat_id, run_id=f"compact:{chat_id}")
        try:
            res = await memory.compact(chat_id, body.model, ctx, lambda step: q.put({"type": "compact", "step": step, "done": step >= 4}))
            text = compact_note(res)
            memory.add_message(chat_id, "sys", text)
            await q.put({"type": "note", "text": text})
            await q.put({"type": "context", **(await memory.meter(chat_id, body.model))})
            await q.put({"type": "cost", "calls": ctx.meter.calls, "usd": round(ctx.meter.usd, 6)})
            await q.put({"type": "done", "monthUsd": round(usage.month_spent(), 6)})
        except Exception as e:
            log.exception("compact failed")
            await q.put({"type": "error", "message": f"Summarizing failed ({type(e).__name__})."})
        await q.put(None)

    asyncio.create_task(work())
    return sse(q)


@router.post("/api/chats/{chat_id}/fork")
async def fork_chat(chat_id: str, body: CompactRequest):
    _chat_or_404(chat_id)
    usage.ensure_can_spend()
    ctx = CallContext(meter=CostMeter(budget=usage.limit_budget(body.maxCost)), chat_id=chat_id, run_id=f"fork:{chat_id}")
    try:
        return await memory.fork_with_summary(chat_id, body.model, ctx)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(422, str(e))


@router.get("/api/chats/{chat_id}/export")
async def export_chat(chat_id: str, includeFiles: bool = False, x_export_password: str | None = Header(default=None)):
    """The password travels in a header, never in the URL, so it cannot end up in access logs or history."""
    try:
        data = await asyncio.to_thread(portability.build_export, chat_id, includeFiles, x_export_password)
    except portability.ExportError as e:
        raise HTTPException(e.status, str(e))
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="chat_{chat_id}.zip"'})


@router.post("/api/import")
async def import_chat(file: UploadFile = File(...), password: str | None = Form(default=None)):
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "The file is larger than 200 MB")
    try:
        return await portability.import_chat(data, password=password)
    except portability.ExportError as e:
        raise HTTPException(e.status, str(e))
