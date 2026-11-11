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


_TITLES = {
    "shared/system_rules": "Shared answer rules",
    "shared/documents_header": "Document context rules",
    "router/route": "Mode router",
    "checker/check": "Answer checker",
    "thinker/agent": "Thinker agent instructions",
    "thinker/composer": "Thinker composer",
    "thinker/judge": "Debate agreement judge",
    "planner/plan_writer": "Planner plan writer",
    "planner/step": "Planner step task",
}
_USER_TEMPLATES = {"simple/retry", "thinker/board", "thinker/composer", "thinker/composer_retry", "planner/step"}


def catalog() -> list[dict[str, str]]:
    """Reviewable shipped templates only. Never render or return user/file/tool/runtime content."""
    out: list[dict[str, str]] = []
    for name in names():
        if name == "gateway/refusal":
            role = "response template"
        elif name in _USER_TEMPLATES:
            role = "user follow-up"
        elif name.startswith("thinker/roles/") or name.startswith("planner/form_") or name in {"shared/documents_header", "skills/header", "thinker/agent"}:
            role = "system fragment"
        else:
            role = "system"
        title = _TITLES.get(name) or name.replace("/", " / ").replace("_", " ").title()
        out.append({"id": name, "title": title, "role": role, "content": _template(name).template})
    return out
