"""Prompt library. Every system prompt used by an agent, sub-agent or team lives in a .md file here,
so prompts can be read, reviewed and edited without touching Python.

    from app import prompts
    prompts.render("checker/check")                         # no placeholders
    prompts.render("planner/step", goal=..., task=...)      # $placeholders filled in

Format of a prompt file:
  * an optional leading <!-- comment --> that says where the prompt is used (stripped at load time)
  * the prompt text, with $name placeholders (Python string.Template); write $$ for a literal dollar sign
A missing placeholder raises KeyError, so a typo fails loudly in the tests instead of silently in a run.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parent
_COMMENT = re.compile(r"^\s*<!--.*?-->\s*", re.S)


@lru_cache(maxsize=None)
def _template(name: str) -> Template:
    path = (PROMPTS_DIR / f"{name}.md").resolve()
    if PROMPTS_DIR not in path.parents:
        raise KeyError(f"prompt name outside the prompts folder: {name}")
    return Template(_COMMENT.sub("", path.read_text(encoding="utf-8")).strip())


def render(name: str, **values: object) -> str:
    """Load `prompts/<name>.md` and fill its $placeholders."""
    return _template(name).substitute({k: str(v) for k, v in values.items()})


def names() -> list[str]:
    """Every prompt in the library, as names usable with render()."""
    return sorted(p.relative_to(PROMPTS_DIR).with_suffix("").as_posix() for p in PROMPTS_DIR.rglob("*.md") if p.name != "README.md")


def placeholders(name: str) -> set[str]:
    return {m.group("named") or m.group("braced") for m in _template(name).pattern.finditer(_template(name).template)
            if m.group("named") or m.group("braced")}
