"""Request bodies. Field names are camelCase to match the frontend exactly. Every size is bounded."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import LIMITS

ModelId = Field(min_length=1, max_length=200)


class SimpleCfg(BaseModel):
    model: str = ModelId
    thinking: Literal["off", "low", "medium", "high"] = "off"
    style: Literal["precise", "balanced", "creative"] = "balanced"
    tools: dict[str, bool] = Field(default_factory=dict)
    maxTokens: int = Field(default=1200, ge=256, le=8192)


class TeamCfg(BaseModel):
    source: Literal["same", "mixed"] = "same"
    model: str = ModelId
    agents: int = 3
    mixed: list[str] = Field(default_factory=list, max_length=10)
    style: Literal["independent", "together"] = "independent"
    rounds: int = 2
    composer: str = Field(default="auto", max_length=200)

    def clamped(self) -> dict:
        """The fixed safety limits (2 to 5 agents, 1 to 3 rounds) apply whatever the client sends."""
        d = self.model_dump()
        d["agents"] = max(LIMITS.min_agents, min(self.agents, LIMITS.max_agents))
        d["rounds"] = max(LIMITS.min_rounds, min(self.rounds, LIMITS.max_rounds))
        d["mixed"] = list(dict.fromkeys(self.mixed))[:LIMITS.max_agents]
        return d


class RunRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    chatId: str = Field(min_length=1, max_length=64)
    mode: Literal["auto", "simple", "thinker", "planner"] = "auto"
    prompt: str = Field(min_length=1, max_length=60000)
    files: list[str] = Field(default_factory=list, max_length=50)
    simple: SimpleCfg
    team: TeamCfg
    runIn: Literal["auto", "simple", "thinker"] = "auto"
    planModel: str | None = Field(default=None, min_length=1, max_length=200)
    budgetUsd: float = Field(default=0.25, ge=0.0, le=50.0)
    allowOver: bool = False
    retryOf: str | None = Field(default=None, max_length=64)


class EstimateRequest(BaseModel):
    mode: Literal["auto", "simple", "thinker", "planner"] = "auto"
    chatId: str | None = Field(default=None, max_length=64)
    prompt: str = Field(default="", max_length=60000)
    simple: SimpleCfg
    team: TeamCfg
    runIn: Literal["auto", "simple", "thinker"] = "auto"
    planModel: str | None = Field(default=None, min_length=1, max_length=200)


class ReadRequest(BaseModel):
    chatId: str = Field(min_length=1, max_length=64)
    reader: Literal["auto", "text", "local", "api", "vision"] = "auto"
    textOnly: bool = False
    maxCost: float | None = Field(default=None, ge=0, le=50, allow_inf_nan=False)
    pages: list[int] | None = Field(default=None, max_length=2000)


class CompactRequest(BaseModel):
    model: str = ModelId
    maxCost: float = Field(default=0.25, ge=0, le=50)


class ReindexRequest(BaseModel):
    chatId: str = Field(min_length=1, max_length=64)
    maxCost: float = Field(ge=0, le=50)


class EditRequest(BaseModel):
    note: str = Field(min_length=1, max_length=1000)
    planVersion: str | None = Field(default=None, max_length=64)


class ApprovalRequest(BaseModel):
    planVersion: str | None = Field(default=None, max_length=64)


class PermissionRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    allow: bool


class TeamStepRequest(BaseModel):
    step: int = Field(ge=0, lt=20)


class RatingRequest(BaseModel):
    value: Literal[-1, 1]


class ChatCreate(BaseModel):
    title: str = Field(default="New chat", max_length=200)
    temp: bool = False


class ChatPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
