"""What every tool is made of. A tool is plain async Python code the model can ask to run.

    Tool        name, the JSON schema the model sees, the setting that turns it on, and run()
    ToolRun     per-run state shared by the tools of one answer (chat, cost context, links found)
    ToolResult  the text that goes back to the model, a short label for the UI, and citations
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable

from app.llm import CallContext


@dataclass
class ToolResult:
    text: str                              # what the model reads (always wrapped as DATA for outside content)
    ok: bool = True
    done_label: str = ""                   # the UI chip: "Used 5 web sources"
    citations: list[str] = field(default_factory=list)


@dataclass
class ToolRun:
    """State shared by every tool call inside one answer."""
    chat_id: str
    ctx: CallContext | None = None
    cite_n: int = 0                        # running source number, so [n] is never ambiguous across searches
    allowed_urls: dict[str, int] = field(default_factory=dict)   # links web_search returned -> their [n]
    allowed_tools: set[str] = field(default_factory=set)
    permission: Callable[[str, dict], Awaitable[bool]] | None = None
    calls: int = 0
    max_calls: int = 10
    scope_id: str = "answer"
    _citation_counter: list[int] = field(default_factory=lambda: [0], repr=False)

    def next_citation(self) -> int:
        self._citation_counter[0] += 1
        self.cite_n = self._citation_counter[0]
        return self.cite_n

    def child(self, scope_id: str) -> "ToolRun":
        """One answer/step has one counter across retries, while facts/citations remain shared."""
        return ToolRun(chat_id=self.chat_id, ctx=self.ctx, allowed_urls=self.allowed_urls, permission=self.permission,
                       max_calls=self.max_calls, scope_id=scope_id, _citation_counter=self._citation_counter)


@dataclass(frozen=True)
class Tool:
    name: str
    setting: str                           # the Setup switch that turns it on: "web" | "code" | "files"
    description: str
    parameters: dict
    run: Callable[[dict, ToolRun], Awaitable[ToolResult]]
    running_label: Callable[[dict], str]
    risky: bool = False                    # writes files, sends messages or runs code outside a sandbox (C11)
    available: bool = True
    why_unavailable: str = ""

    def spec(self) -> dict:
        """The OpenAI-style function schema sent to the model."""
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}
