"""Stage 1, Input Gateway: the safety check (C1). History, memory and files are added by the Context Builder,
and the one clarifying question (C2) comes from the router.

This is a deliberately small first line of defense: a deny-list for clearly harmful requests, checked
before any model call. Production should add a moderation model. Prompt-injection text inside files, web
pages or imported chats is NOT refused here; it is wrapped as DATA in every prompt (C44).
"""
from __future__ import annotations

import re

from app import prompts

_HARM = [
    r"\b(synthesi[sz]e|make|build|produce|manufacture|cook)\b.{0,50}\b(sarin|vx gas|nerve agent|mustard gas|anthrax|ricin|bioweapon|chemical weapon|dirty bomb|pipe bomb|nail bomb)\b",
    r"\b(write|create|build|code)\b.{0,40}\b(ransomware|keylogger|botnet|computer worm|credential stealer)\b",
    r"\b(child|minor|underage)\b.{0,30}\b(sexual|porn|nude|explicit)\b",
]
_HARM_RE = [re.compile(p, re.I | re.S) for p in _HARM]


def check_input(text: str) -> tuple[bool, str]:
    """(ok, reason). Unsafe -> refuse and say why."""
    if any(rx.search(text) for rx in _HARM_RE):
        return False, prompts.render("gateway/refusal")
    return True, ""
