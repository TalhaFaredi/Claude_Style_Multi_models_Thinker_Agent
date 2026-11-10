"""Cost Meter + Budget Guard (spec Part 1 section 3): counts tokens and money for every call and
stops the run at the budget."""
from __future__ import annotations

import threading
import math
from dataclasses import dataclass, field


def usd(v: float) -> str:
    """Money for people: $0.25, but $0.00002 for tiny amounts instead of a misleading $0.00."""
    return f"${v:.2f}" if v >= 0.01 else f"${v:.5f}".rstrip("0").rstrip(".") if v > 0 else "$0"


class BudgetExceeded(Exception):
    """Raised before a call that would push the run past its budget (C20: stop, keep progress)."""

    def __init__(self, spent: float, budget: float, next_estimate: float):
        super().__init__(f"Budget {usd(budget)} would be exceeded (spent {usd(spent)}, next call about {usd(next_estimate)})")
        self.spent, self.budget, self.next_estimate = spent, budget, next_estimate


@dataclass
class CostMeter:
    budget: float                       # money cap for this run (USD)
    usd: float = 0.0
    calls: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    cached_tokens: int = 0
    by_stage: dict[str, float] = field(default_factory=dict)
    reserved: float = 0.0
    estimated_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def check(self, estimate: float) -> None:
        """Budget Guard: call before each model call with its worst-case price."""
        with self._lock:
            self._check(estimate)

    def _check(self, estimate: float) -> None:
        if not math.isfinite(estimate) or estimate < 0:
            raise ValueError("A cost estimate must be finite and nonnegative")
        if self.usd + self.reserved + estimate > self.budget + 1e-12:
            raise BudgetExceeded(self.usd + self.reserved, self.budget, estimate)

    def reserve(self, estimate: float) -> "Reservation":
        """Atomically book the request before dispatch, including all concurrent requests."""
        with self._lock:
            self._check(estimate)
            self.reserved += estimate
            return Reservation(self, estimate)

    def add(self, stage: str, usd: float, in_tokens: int, out_tokens: int, cached: int = 0, *, estimated: bool = False) -> None:
        if not math.isfinite(usd) or usd < 0:
            raise ValueError("A charge must be finite and nonnegative")
        with self._lock:
            self._add(stage, usd, in_tokens, out_tokens, cached, estimated)

    def _add(self, stage: str, usd: float, in_tokens: int, out_tokens: int, cached: int, estimated: bool) -> None:
        self.usd += usd
        self.calls += 1
        self.in_tokens += in_tokens
        self.out_tokens += out_tokens
        self.cached_tokens += cached
        self.estimated_calls += int(estimated)
        self.by_stage[stage] = self.by_stage.get(stage, 0.0) + usd

    @property
    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self.budget - self.usd - self.reserved)

    def snapshot(self) -> dict:
        return {"usd": round(self.usd, 6), "calls": self.calls, "inTokens": self.in_tokens, "outTokens": self.out_tokens,
                "cachedTokens": self.cached_tokens, "reservedUsd": round(self.reserved, 6), "estimatedCalls": self.estimated_calls,
                "byStage": {k: round(v, 6) for k, v in self.by_stage.items()}}


@dataclass
class Reservation:
    meter: CostMeter
    estimate: float
    active: bool = True

    def settle(self, stage: str, cost: float, in_tokens: int, out_tokens: int, cached: int = 0, *, estimated: bool = False) -> None:
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("A charge must be finite and nonnegative")
        with self.meter._lock:
            if not self.active:
                raise RuntimeError("Reservation already settled or released")
            self.active = False
            self.meter.reserved = max(0.0, self.meter.reserved - self.estimate)
            self.meter._add(stage, cost, in_tokens, out_tokens, cached, estimated)

    def release(self) -> None:
        with self.meter._lock:
            if self.active:
                self.active = False
                self.meter.reserved = max(0.0, self.meter.reserved - self.estimate)
