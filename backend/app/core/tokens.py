"""Token estimation. Real counts come from the provider's `usage`; this is only for planning
(budget estimates, context building) and is calibrated per chat against the real counts."""
from __future__ import annotations

import math

IMAGE_TOKENS = 1600   # one page image is about 1,600 tokens (spec Part 2 section 4)


def estimate_tokens(text: str) -> int:
    """About 4 characters per token for English; slightly higher for code and non-Latin text."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 3.8))


def estimate_messages(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += estimate_tokens(c)
        elif isinstance(c, list):
            for part in c:
                total += estimate_tokens(part.get("text", "")) if part.get("type") == "text" else IMAGE_TOKENS
        total += 4  # per-message framing
        if m.get("tool_calls"):
            total += estimate_tokens(str(m["tool_calls"]))
    return total
