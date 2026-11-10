"""Skills Hub (spec Part 1 section 3: "Skills are instruction files loaded into the prompt").

A skill is a folder with one SKILL.md file: YAML front matter, then short instructions.

    ---
    name: humanizer
    description: Make text read like a person wrote it.
    triggers: [humanize, sound human, rewrite]      # distinctive words or phrases: one is enough
    hints: [tone, natural]                          # optional: common words; two are needed (or one plus a trigger)
    modes: [simple, thinker, planner]               # where it may be used
    formats: [text]                                 # output formats it serves (pdf, html, md, code, text, plan)
    source: https://github.com/blader/humanizer (MIT), rewritten short for this app
    ---
    instructions ...

How a skill is chosen for one question:
  * a format match (for example the Planner is building a PDF -> pdf-report) scores 5
  * every trigger found in the question scores 2, every hint scores 1; a skill needs at least 2
    (measured: one common word such as "color", "why", "list" or "plan" picked a wrong skill in 5 of 22 prompts,
    and "my favorite color is teal" got design advice)
  * the best 1 or 2 skills that fit the token budget are added to the prompt, right before the new
    message, so the cached start of the prompt stays the same from turn to turn (cheap cached reads)
Skills are files in this repository: users and model output can never add or change one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app import prompts
from app.core.tokens import estimate_tokens

SKILLS_DIR = Path(__file__).resolve().parent
ALL_MODES = ("simple", "thinker", "planner")
MIN_SCORE = 2   # one trigger, two hints, or a format match


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    triggers: tuple[str, ...]
    modes: tuple[str, ...]
    formats: tuple[str, ...]
    source: str
    body: str
    hints: tuple[str, ...] = ()

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.body) + 8

    def score(self, text: str, fmt: str | None) -> int:
        low = text.lower()

        def found(words: tuple[str, ...]) -> int:
            return sum(1 for t in words if re.search(rf"(?<!\w){re.escape(t.lower())}(?!\w)", low))
        return (5 if fmt and fmt in self.formats else 0) + 2 * found(self.triggers) + found(self.hints)


def parse_skill(path: Path) -> Skill:
    """Read one SKILL.md. Raises ValueError with the file name if the front matter is wrong."""
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if not m:
        raise ValueError(f"{path}: missing --- front matter ---")
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{path}: front matter is not valid YAML ({e.problem}); quote values that contain ': '") from e
    for key in ("name", "description", "triggers"):
        if not meta.get(key):
            raise ValueError(f"{path}: front matter needs '{key}'")
    modes = tuple(meta.get("modes") or ALL_MODES)
    if set(modes) - set(ALL_MODES):
        raise ValueError(f"{path}: unknown mode in {modes}")
    return Skill(str(meta["name"]), str(meta["description"]), tuple(str(t) for t in meta["triggers"]), modes,
                 tuple(str(f) for f in meta.get("formats") or ()), str(meta.get("source") or "written for this app"), m.group(2).strip(),
                 tuple(str(h) for h in meta.get("hints") or ()))


@lru_cache(maxsize=1)
def all_skills() -> tuple[Skill, ...]:
    return tuple(parse_skill(p) for p in sorted(SKILLS_DIR.glob("*/SKILL.md")))


def get(name: str) -> Skill | None:
    return next((s for s in all_skills() if s.name == name), None)


def select(text: str, *, mode: str, fmt: str | None = None, limit: int = 2, budget_tokens: int = 900) -> list[Skill]:
    """The skills this question needs, best first, inside the token budget."""
    scored = [(s.score(text, fmt), s) for s in all_skills() if mode in s.modes]
    scored = sorted(((n, s) for n, s in scored if n >= MIN_SCORE), key=lambda x: (-x[0], x[1].tokens))
    out, used = [], 0
    for _, s in scored:
        if len(out) >= limit:
            break
        if used + s.tokens <= budget_tokens:
            out.append(s)
            used += s.tokens
    return out


def render(chosen: list[Skill]) -> str:
    """The <skills> block for the prompt ('' when no skill applies)."""
    if not chosen:
        return ""
    body = "\n\n".join(f"## Skill: {s.name}\n{s.body}" for s in chosen)
    return f"<skills>\n{prompts.render('skills/header')}\n\n{body}\n</skills>"


def catalog() -> list[dict]:
    """What GET /api/skills shows: every skill with where it is used and where it came from."""
    return [{"name": s.name, "description": s.description, "modes": list(s.modes), "formats": list(s.formats),
             "triggers": list(s.triggers), "source": s.source, "tokens": s.tokens} for s in all_skills()]
