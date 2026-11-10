"""C9: tools are needed but the chosen model has no tool support -> use a tool-capable model, or answer
without tools and say so."""
from __future__ import annotations

from app.llm import registry


def pick_model_for_tools(model_id: str, want_tools: bool) -> tuple[str, bool]:
    """(model to use, tools usable)."""
    if not want_tools or registry.get(model_id).tools:
        return model_id, want_tools
    alt = next(iter(registry.fallbacks(model_id, need_tools=True)), None)
    return (alt, True) if alt else (model_id, False)
