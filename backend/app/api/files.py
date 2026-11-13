"""Files: upload (free page check), read (Parse Cache, cost check), detach, and generated-file downloads."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import files, memory, output
from app.api.schemas import ReadRequest, ReindexRequest
from app.core.config import MAX_UPLOAD_BYTES
from app.core.privacy import is_fingerprint

router = APIRouter()

# Generated files are model output: a browser must never run or sniff them as a page on the API's origin.
DOWNLOAD_HEADERS = {"Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"}


def _own_file(chat_id: str, fp: str) -> None:
    if not is_fingerprint(fp) or not files.is_linked(chat_id, fp):
        raise HTTPException(404, "Unknown file")


@router.post("/api/chats/{chat_id}/files")
async def upload_file(chat_id: str, file: UploadFile = File(...)):
    memory.ensure_chat(chat_id)   # before the body is read: someone else's chat id is refused without buffering the upload
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        return await asyncio.to_thread(files.ingest, chat_id, file.filename or "upload", data)
    except files.FileError as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/files/{fp}")
async def file_info(fp: str, chatId: str):
    _own_file(chatId, fp)
    return files.file_status(fp)


@router.post("/api/files/{fp}/read")
async def read_file(fp: str, body: ReadRequest):
    try:
        return await files.read_file(body.chatId, fp, body.reader, body.textOnly, body.maxCost, body.pages)
    except files.FileError as e:
        raise HTTPException(e.status, detail={"message": str(e), **e.extra})


@router.post("/api/files/{fp}/read-estimate")
async def reading_estimate(fp: str, body: ReadRequest):
    _own_file(body.chatId, fp)
    try:
        return files.reading_estimate(body.chatId, fp, body.reader, body.textOnly, body.pages)
    except files.FileError as e:
        raise HTTPException(e.status, detail={"message": str(e), **e.extra})


@router.delete("/api/chats/{chat_id}/files/{fp}")
async def detach_file(chat_id: str, fp: str):
    _own_file(chat_id, fp)
    files.detach(chat_id, fp)
    return {"ok": True}


@router.get("/api/files/{fp}/reindex-estimate")
async def reindex_estimate(fp: str, chatId: str):
    _own_file(chatId, fp)
    try:
        return files.reindex_estimate(chatId, fp)
    except files.FileError as e:
        raise HTTPException(e.status, detail={"message": str(e), **e.extra})


@router.post("/api/files/{fp}/reindex")
async def reindex_file(fp: str, body: ReindexRequest):
    _own_file(body.chatId, fp)
    try:
        return await files.reindex_file(body.chatId, fp, body.maxCost)
    except files.FileError as e:
        raise HTTPException(e.status, detail={"message": str(e), **e.extra})


@router.get("/api/artifacts/{artifact_id}")
async def download_artifact(artifact_id: str):
    a = output.get_artifact(artifact_id)
    if not a:
        raise HTTPException(404, "Unknown file")
    return FileResponse(a["path"], media_type=a["mime"] or "application/octet-stream", filename=a["name"], headers=DOWNLOAD_HEADERS)
