"""Tiny SSE client used by the live integration scripts (they spend real, but tiny, amounts of credit)."""
from __future__ import annotations

import json
import time
import uuid

import httpx

BASE = "http://localhost:8000"
FAST = "meta-llama/llama-3.1-8b-instruct"
BAL = "qwen/qwen3.7-flash"


def payload(chat_id: str, prompt: str, mode: str = "simple", **over) -> dict:
    p = {
        "id": uuid.uuid4().hex[:10], "chatId": chat_id, "mode": mode, "prompt": prompt, "files": [],
        "simple": {"model": BAL, "thinking": "off", "style": "balanced", "tools": {"web": False, "code": False, "files": True}},
        "team": {"source": "same", "model": FAST, "agents": 3, "mixed": [], "style": "independent", "rounds": 2, "composer": "auto"},
        "runIn": "auto", "budgetUsd": 0.25, "allowOver": False,
    }
    p.update(over)
    return p


def stream(c: httpx.Client, p: dict, on_event=None, timeout: float = 240) -> list[dict]:
    events: list[dict] = []
    with c.stream("POST", f"{BASE}/api/runs", json=p, timeout=timeout) as r:
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.read()[:300]}")
        for line in r.iter_lines():
            if line.startswith("data:"):
                e = json.loads(line[5:])
                events.append(e)
                if on_event:
                    on_event(e)
    return events


def summarize(events: list[dict]) -> dict:
    text = ""
    for e in events:
        if e["type"] == "text":
            text = e["delta"] if e.get("replace") else text + e["delta"]
    types: dict[str, int] = {}
    for e in events:
        types[e["type"]] = types.get(e["type"], 0) + 1
    cost = [e for e in events if e["type"] == "cost"]
    ctx = [e for e in events if e["type"] == "context"]
    return {"types": types, "text": text, "cost": cost[-1] if cost else None, "context": ctx[-1] if ctx else None,
            "statuses": [e["text"] for e in events if e["type"] == "status"],
            "warnings": [e["message"] for e in events if e["type"] == "warning"],
            "errors": [e["message"] for e in events if e["type"] == "error"],
            "done": any(e["type"] == "done" for e in events)}


def client() -> httpx.Client:
    return httpx.Client(timeout=120)
