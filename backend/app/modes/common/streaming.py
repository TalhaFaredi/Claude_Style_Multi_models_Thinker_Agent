"""Answer settings and streaming helpers shared by the modes."""
from __future__ import annotations

from app.core import config
from app.pipeline.runtime import RunContext

STYLE_TEMP = {"precise": 0.2, "balanced": 0.7, "creative": 1.0}   # Setup: style Precise / Balanced / Creative
DEFAULT_MAX_TOKENS = 1500


def stream_now() -> bool:
    """Stream the draft while it is written (the Checker can still replace it), unless STREAM_BEFORE_CHECK=0."""
    return config.STREAM_BEFORE_CHECK


async def emit_buffered(rc: RunContext, text: str) -> None:
    """When the draft was held until it passed the Checker, release it in small pieces."""
    for i in range(0, len(text), 40):
        await rc.text(text[i:i + 40])


async def skills_note(rc: RunContext, names: list[str]) -> None:
    if names:
        await rc.status("Using skills: " + ", ".join(names))
