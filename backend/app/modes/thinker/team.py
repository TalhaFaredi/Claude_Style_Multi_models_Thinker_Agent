"""The team: who the agents are (spec section 7, "Team cases").

Same model -> 2 to 5 copies, each with its own role AND temperature (five identical copies would add cost,
not ideas). Different models -> 2 to 5 models, each an independent expert. Role texts live in
app/prompts/thinker/roles/.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from app import prompts
from app.core.config import LIMITS
from app.llm import registry
from app.pipeline.runtime import RunContext

# (role shown to the composer and the UI, prompt file in prompts/thinker/roles/, temperature)
SAME_MODEL_ROLES = [("Solver", "solver", 0.3), ("Critic", "critic", 0.5), ("Fact-checker", "fact_checker", 0.7),
                    ("Simplifier", "simplifier", 0.9), ("Devil's advocate", "devils_advocate", 1.0)]


@dataclass
class Agent:
    role: str
    role_file: str
    model: str
    temp: float
    alive: bool = True
    status: str = "thinking"
    answer: str = ""
    first: str = ""        # round-1 answer: the composer sees it after a debate, so copying shows (T8)
    changed: str = ""      # "Changed because: ..." / "Unchanged"

    def role_prompt(self) -> str:
        return prompts.render(f"thinker/roles/{self.role_file}")


def build_agents(team: dict) -> list[Agent]:
    if team.get("source", "same") == "same":
        n = max(LIMITS.min_agents, min(int(team.get("agents", 3)), LIMITS.max_agents))
        return [Agent(role, file, team["model"], temp) for role, file, temp in SAME_MODEL_ROLES[:n]]
    return [Agent(f"Agent {i + 1}", "independent", m, 0.7) for i, m in enumerate((team.get("mixed") or [])[:LIMITS.max_agents])]


def tier_warning(agents: list[Agent]) -> str:
    """T5 / F13: strong and weak models mixed."""
    tiers = [registry.get(a.model).tier for a in agents]
    return "Strong and weak models are mixed; a weak model can pull the answer down." if tiers and max(tiers) - min(tiers) >= 2 else ""


def team_line(team: dict) -> str:
    """'3 x Llama 3.1 8B, on their own' — the progress line and Planner step labels."""
    who = (f"{team.get('agents', 3)} x {registry.get(team['model']).name}" if team.get("source", "same") == "same"
           else f"{len(team.get('mixed') or [])} different models")
    return f"{who}, " + (f"together, {team.get('rounds', 2)} rounds" if team.get("style") == "together" else "on their own")


@dataclass
class Progress:
    """Where team progress goes: agent cards in Thinker mode, or one note on the plan card inside a Planner step."""
    rc: RunContext
    quiet: bool = False
    on_note: Callable[[str], Awaitable[None]] | None = None

    async def push(self, agents: list[Agent], round_text: str) -> None:
        if self.quiet:
            if self.on_note:
                await self.on_note(round_text)
            return
        await self.rc.emit({"type": "agents", "roundText": round_text,
                            "agents": [{"role": a.role, "model": registry.get(a.model).name, "status": a.status} for a in agents if a.alive]})
