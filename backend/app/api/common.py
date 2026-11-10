"""Helpers shared by the route modules: Server-Sent Events and the default Setup choices."""
from __future__ import annotations

import asyncio
import json

from fastapi.responses import StreamingResponse

from app.llm import QUALITY_PRESETS

SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


async def _events(q: asyncio.Queue):
    while True:
        try:
            item = await asyncio.wait_for(q.get(), 15)
        except asyncio.TimeoutError:
            yield ": ping\n\n"   # keeps proxies from closing a quiet stream
            continue
        if item is None:
            return
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"


def sse(q: asyncio.Queue) -> StreamingResponse:
    """Stream a queue of events; `None` ends the stream."""
    return StreamingResponse(_events(q), media_type="text/event-stream", headers=SSE_HEADERS)


def defaults() -> dict:
    """Safe, cheap defaults for the Setup dialog."""
    fast, bal = QUALITY_PRESETS["fast"], QUALITY_PRESETS["balanced"]
    return {
        "simple": {"model": bal, "thinking": "off", "style": "balanced", "tools": {"web": True, "code": False, "files": True}, "maxTokens": 1200},
        "team": {"source": "same", "model": fast, "agents": 3, "mixed": [fast, "mistralai/mistral-nemo", "google/gemma-3-12b-it"],
                 "style": "independent", "rounds": 2, "composer": "auto"},   # "on their own" is the spec's default
        "runIn": "auto", "budget": 0.25,
    }
