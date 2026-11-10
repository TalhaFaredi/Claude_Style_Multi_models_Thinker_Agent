"""What every mode returns to the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Result:
    text: str = ""
    citations: list[str] = field(default_factory=list)
    warning: str | None = None          # C19: the answer failed its check and retries ran out
    model: str = ""
    output: dict | None = None          # a file the Output Builder made
    partial: bool = False               # C20: stopped at a limit, this is what was done
    extra: object | None = None         # mode-specific data (the Thinker returns its agents for a composer-only retry)
