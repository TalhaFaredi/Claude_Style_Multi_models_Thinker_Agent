"""Long-term memory: list facts (with history) and delete one."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import memory

router = APIRouter()


@router.get("/api/memory")
async def get_memory(history: bool = False):
    return {"facts": memory.list_facts(history), "enabled": memory.get_settings()["longMemory"]}


@router.delete("/api/memory/{fact_id}")
async def delete_memory(fact_id: int):
    if not memory.delete_fact(fact_id):
        raise HTTPException(404, "Unknown fact")
    return {"deleted": True}
