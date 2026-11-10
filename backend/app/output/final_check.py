"""Final safety and format check on every answer (C21: fix once; if it still fails, send plain text)."""
from __future__ import annotations

import re

from app.core.privacy import redact_flag


def final_check(text: str) -> tuple[str, list[str]]:
    """Returns (text to send, notes about what was fixed)."""
    notes: list[str] = []
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).encode("utf-8", "replace").decode("utf-8")
    if clean != text:
        notes.append("Removed invalid control characters from the answer.")
        text = clean
    text, changed = redact_flag(text)
    if changed:
        notes.append("Removed a secret-looking string from the answer.")
    if not text.strip():
        text = "I could not produce an answer. Please try again or rephrase."
        notes.append("Empty answer replaced.")
    return text, notes
