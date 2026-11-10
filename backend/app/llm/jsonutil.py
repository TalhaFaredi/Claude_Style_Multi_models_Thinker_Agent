"""Small helpers for "return JSON only" calls (router, judge, checker, ledger, facts)."""
from __future__ import annotations

import json
import re

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def parse_json(text: str):
    """Lenient JSON extraction: models often wrap JSON in prose or code fences."""
    if not text:
        return None
    t = _FENCE.sub("", text.strip())
    for opener, closer in (("{", "}"), ("[", "]")):
        a, b = t.find(opener), t.rfind(closer)
        if a != -1 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except ValueError:
                continue
    return None


async def ask_json(model: str, system: str, user: str, *, stage: str, ctx=None, max_tokens: int = 400, temperature: float = 0.0):
    """One small-model call that must answer in JSON. Returns (data or None, ChatResult)."""
    from app import llm   # call through the package so tests can swap `llm.complete` in one place
    res = await llm.complete(model, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                             stage=stage, ctx=ctx, temperature=temperature, max_tokens=max_tokens, thinking="off")
    return parse_json(res.text), res
