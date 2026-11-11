"""Model Registry (spec Part 1 section 3): every model with company, price, context size and
tool / image / thinking support. Filled from OpenRouter's live model list; NVIDIA entries are
added by hand because NVIDIA's list has no prices or capabilities (spec Part 1 section 9).

The catalog exposes all OpenRouter entries. Featured models remain the limited automatic
fallback pool so browsing a model cannot silently change the user's spending choices.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import math
from dataclasses import dataclass, field

import httpx

from app.core import config
from app.core.config import DATA_DIR, NVIDIA_KEY, NVIDIA_URL, OPENROUTER_KEY, OPENROUTER_URL

log = logging.getLogger("registry")
NIM_PREFIX = "nim:"

# id, display name, company, tier(1 small .. 3 strong), static fallback caps (tools, vision, thinking)
FEATURED_OPENROUTER = [
    ("meta-llama/llama-3.1-8b-instruct", "Llama 3.1 8B Instruct", "Meta", 1, (True, False, False)),
    ("mistralai/mistral-nemo", "Mistral Nemo", "Mistral", 1, (True, False, False)),
    ("google/gemma-3-12b-it", "Gemma 3 12B", "Google", 1, (True, True, False)),
    ("inclusionai/ling-3.0-flash", "Ling 3.0 Flash", "InclusionAI", 1, (True, False, True)),
    ("openai/gpt-oss-20b", "GPT-OSS 20B", "OpenAI", 2, (True, False, True)),
    ("qwen/qwen3.7-flash", "Qwen 3.7 Flash", "Alibaba", 2, (True, True, True)),
    ("openai/gpt-5-nano", "GPT-5 Nano", "OpenAI", 2, (True, True, True)),
    ("openai/gpt-4.1-nano", "GPT-4.1 Nano", "OpenAI", 2, (True, True, False)),
    ("google/gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite", "Google", 2, (True, True, True)),
    ("openai/gpt-oss-120b", "GPT-OSS 120B", "OpenAI", 3, (True, False, True)),
    ("deepseek/deepseek-chat", "DeepSeek Chat", "DeepSeek", 3, (True, False, False)),
    ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Anthropic", 3, (True, True, True)),
]

# NVIDIA NIM hosted models (hand-entered). Price unknown -> 0 (free trial credits), flagged price_known=False.
FEATURED_NVIDIA = [
    ("meta/llama-3.2-90b-vision-instruct", "Llama 3.2 90B Vision (NIM)", "Meta", 3, (False, True, False), 131072),
    ("nvidia/llama-3.1-nemotron-70b-instruct", "Nemotron 70B (NIM)", "NVIDIA", 2, (True, False, False), 131072),
    ("nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super 120B (NIM)", "NVIDIA", 3, (True, False, True), 131072),
    ("google/gemma-3-12b-it", "Gemma 3 12B (NIM)", "Google", 1, (False, True, False), 131072),
    ("deepseek-ai/deepseek-v4.1-flash", "DeepSeek V4.1 Flash (NIM)", "DeepSeek", 2, (True, False, True), 131072),
]

# Presets the UI offers for Auto ("Fast / Balanced / Best"). All cheap on purpose for testing.
QUALITY_PRESETS = {
    "fast": "meta-llama/llama-3.1-8b-instruct",
    "balanced": "qwen/qwen3.7-flash",
    "best": "openai/gpt-oss-120b",
}

TYPICAL_IN, TYPICAL_OUT = 1500, 600   # tokens used for the "price of one typical call" figure
TOKEN_BANDS = {"small": (1_000, 5_000), "medium": (5_000, 50_000), "high": (50_000, 500_000)}


@dataclass
class ModelInfo:
    id: str
    name: str
    company: str
    provider: str                       # "openrouter" | "nvidia"
    tools: bool
    vision: bool
    thinking: bool
    context: int
    price_in: float                     # USD per 1M input tokens
    price_out: float                    # USD per 1M output tokens
    tier: int = 2
    featured: bool = False
    price_known: bool = True
    available: bool = True
    why_unavailable: str = ""
    api_id: str = ""                    # id sent to the provider (no "nim:" prefix)
    price_cache_read: float | None = None
    price_cache_write: float | None = None
    price_request: float = 0.0
    chat_compatible: bool = True
    price_overrides: list[dict] = field(default_factory=list)

    def applicable_overrides(self, input_tokens: int):
        for override in self.price_overrides:
            if not isinstance(override, dict):
                continue
            try:
                threshold = int(override.get("min_prompt_tokens") or 0)
            except (TypeError, ValueError, OverflowError):
                continue
            if input_tokens <= threshold and threshold > 0:
                continue
            yield override

    def quote_rates(self, input_tokens: int) -> tuple[float, float]:
        """Conservative rates for any applicable long-context/time-window override."""
        price_in, price_out = self.price_in, self.price_out
        for override in self.applicable_overrides(input_tokens):
            override_in = _optional_price(override.get("prompt"))
            override_out = _optional_price(override.get("completion"))
            if override_in is not None:
                price_in = max(price_in, override_in)
            if override_out is not None:
                price_out = max(price_out, override_out)
        return price_in, price_out

    def tentative_costs(self) -> dict:
        """Illustrative ONE-call costs at a disclosed 70% input / 30% output split.

        No cache discounts, tools, retries, reasoning allowance or other agents are assumed.
        A partly fitting band ends at the model's actual context length.
        """
        bands = {}
        for label, (minimum, maximum) in TOKEN_BANDS.items():
            upper = min(maximum, self.context)
            usable = self.price_known and self.chat_compatible and self.context >= minimum
            def amount(tokens: int) -> float:
                inp = int(tokens * 0.7)
                pin, pout = self.quote_rates(inp)
                return (inp * pin + (tokens - inp) * pout) / 1_000_000 + self.price_request
            bands[label] = {
                "minTokens": minimum, "maxTokens": upper if usable else maximum,
                "minUsd": round(amount(minimum), 8) if usable else None,
                "maxUsd": round(amount(upper), 8) if usable else None,
                "fits": self.context >= maximum,
                "available": bool(usable),
            }
        return bands

    def call_cost(self, tin: int = TYPICAL_IN, tout: int = TYPICAL_OUT, cached: int = 0, cache_write: int = 0) -> float:
        """Use model-specific cache rates; actual provider-reported cost remains authoritative."""
        cached = max(0, min(tin, cached))
        cache_write = max(0, min(tin - cached, cache_write))
        fresh = max(0, tin - cached - cache_write)
        price_in, price_out = self.quote_rates(tin)
        multiplier = 0.05 if self.id.startswith(("anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5")) else (0.1 if self.id.startswith("anthropic/") else 1)
        read = self.price_cache_read if self.price_cache_read is not None else price_in * multiplier
        write = self.price_cache_write if self.price_cache_write is not None else price_in * (2 if db_cache_ttl() == "1h" else 1.25)
        for override in self.applicable_overrides(tin):
            read = max(read, _optional_price(override.get("input_cache_read")) or 0.0)
            key = "input_cache_write_1h" if db_cache_ttl() == "1h" else "input_cache_write"
            write = max(write, _optional_price(override.get(key)) or 0.0)
        if self.id.startswith("anthropic/") and db_cache_ttl() == "1h":
            write = max(write, price_in * 2)
        return (fresh * price_in + cached * read + cache_write * write + tout * price_out) / 1_000_000 + self.price_request

    def cost_level(self) -> str:
        p = self.price_out
        return "$" if p <= 0.5 else "$$" if p <= 2.0 else "$$$"

    def to_api(self) -> dict:
        from app.core import db
        latency = db.one("SELECT AVG(ms) ms FROM calls WHERE model=? AND ok=1 AND ms>0", (self.id,))
        speed = f"{float(latency['ms']) / 1000:.1f}s average response" if latency and latency["ms"] is not None else "Not measured"
        return {
            "id": self.id, "name": self.name, "company": self.company, "provider": self.provider,
            "tools": self.tools, "vision": self.vision, "thinking": self.thinking,
            "costLevel": self.cost_level() if self.price_known else "unknown", "tier": self.tier,
            "callCost": round(self.call_cost(), 6) if self.price_known else None,
            "priceIn": self.price_in, "priceOut": self.price_out, "context": self.context,
            "priceKnown": self.price_known, "available": self.available, "whyUnavailable": self.why_unavailable,
            "featured": self.featured,
            "priceCacheRead": self.price_cache_read, "priceCacheWrite": self.price_cache_write,
            "priceRequest": self.price_request,
            "chatCompatible": self.chat_compatible,
            "tentativeCosts": self.tentative_costs(),
            "pricingNote": "One call, 70% input / 30% output tokens; conditional pricing uses conservative rates. Excludes reasoning, cache discounts, tools, retries, checker and other agents. Actual cost appears after each call.",
            "speed": speed,
        }


@dataclass
class Registry:
    models: dict[str, ModelInfo] = field(default_factory=dict)
    provider_status: dict[str, dict] = field(default_factory=dict)
    loaded_at: float = 0.0

    # ------------------------------------------------------------------ loading
    async def load(self, force: bool = False) -> None:
        cache = DATA_DIR / "openrouter_models.json"
        raw: list[dict] | None = None
        if not force and cache.exists() and time.time() - cache.stat().st_mtime < 24 * 3600:
            try:
                raw = json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                raw = None
        if raw is None:
            try:
                async with httpx.AsyncClient(timeout=30) as c:
                    r = await c.get(f"{OPENROUTER_URL}/models")
                    r.raise_for_status()
                    raw = r.json()["data"]
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(raw), encoding="utf-8")
            except Exception as e:
                log.warning("OpenRouter model list unavailable (%s); using the static featured list", e)
                raw = []
        self._build(raw)

    def _build(self, raw: list[dict]) -> None:
        live = {m["id"]: m for m in raw if isinstance(m, dict) and isinstance(m.get("id"), str)}
        featured_ids = {f[0]: f for f in FEATURED_OPENROUTER}
        models: dict[str, ModelInfo] = {}
        for mid, m in live.items():
            sp = m.get("supported_parameters") or []
            architecture = m.get("architecture") or {}
            mods = architecture.get("input_modalities") or []
            output_mods = architecture.get("output_modalities") or []
            endpoints = m.get("endpoints") or []
            compatible = ((not mods or "text" in mods) and (not output_mods or "text" in output_mods)
                          and (not endpoints or "/api/v1/chat/completions" in endpoints))
            pr = m.get("pricing") or {}
            pin, pout = _optional_price(pr.get("prompt")), _optional_price(pr.get("completion"))
            request_fee = _optional_fee(pr.get("request"))
            price_known = pin is not None and pout is not None and request_fee is not None
            try:
                context = int(m.get("context_length") or 0)
            except (TypeError, ValueError, OverflowError):
                context = 0
            f = featured_ids.get(mid)
            models[mid] = ModelInfo(
                id=mid, name=(f[1] if f else m.get("name") or mid), company=(f[2] if f else mid.split("/")[0].title()),
                provider="openrouter", tools="tools" in sp, vision="image" in mods, thinking="reasoning" in sp,
                context=context, price_in=pin or 0.0, price_out=pout or 0.0,
                tier=(f[3] if f else 2), featured=bool(f), price_known=price_known and context > 0, api_id=mid,
                price_cache_read=_optional_price(pr.get("input_cache_read")), price_cache_write=_optional_price(pr.get("input_cache_write")),
                price_request=request_fee or 0.0, chat_compatible=compatible,
                price_overrides=pr.get("overrides") if isinstance(pr.get("overrides"), list) else [],
            )
        for mid, name, co, tier, (t, v, th) in FEATURED_OPENROUTER:
            if mid not in models:   # offline fallback so the app still lists them
                models[mid] = ModelInfo(mid, name, co, "openrouter", t, v, th, 131072, 0.05, 0.2, tier, True, False, api_id=mid)
        for mid, name, co, tier, (t, v, th), ctx in FEATURED_NVIDIA:
            uid = NIM_PREFIX + mid
            pin = _configured_price("NVIDIA_INPUT_USD_PER_MILLION")
            pout = _configured_price("NVIDIA_OUTPUT_USD_PER_MILLION")
            models[uid] = ModelInfo(uid, name, co, "nvidia", t, v, th, ctx, pin or 0.0, pout or 0.0, tier, True,
                                    pin is not None and pout is not None, api_id=mid)
        self.models = models
        self.loaded_at = time.time()
        self._apply_status()

    # ------------------------------------------------------------------ provider health
    async def probe_providers(self) -> dict[str, dict]:
        """Check each provider key once. Models of a provider that fails are marked unavailable with the reason."""
        status: dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=25) as c:
            if not OPENROUTER_KEY:
                status["openrouter"] = {"ok": False, "reason": "No OpenRouter key found in .env"}
            else:
                try:
                    r = await c.get(f"{OPENROUTER_URL}/key", headers={"Authorization": f"Bearer {OPENROUTER_KEY}"})
                    d = (r.json() or {}).get("data", {}) if r.status_code == 200 else {}
                    status["openrouter"] = {"ok": r.status_code == 200, "reason": "" if r.status_code == 200 else f"HTTP {r.status_code}",
                                            "creditRemaining": d.get("limit_remaining"), "creditLimit": d.get("limit")}
                except Exception as e:
                    status["openrouter"] = {"ok": False, "reason": f"unreachable: {type(e).__name__}"}
            if not NVIDIA_KEY:
                status["nvidia"] = {"ok": False, "reason": "No NVIDIA key found in .env"}
            else:
                try:
                    # A health check must not silently spend inference credits.
                    r = await c.get(f"{NVIDIA_URL}/models", headers={"Authorization": f"Bearer {NVIDIA_KEY}"})
                    ok = r.status_code == 200
                    status["nvidia"] = {"ok": ok, "reason": "" if ok else ("Key not authorized for NVIDIA inference (HTTP 403)" if r.status_code == 403 else f"HTTP {r.status_code}")}
                except Exception as e:
                    status["nvidia"] = {"ok": False, "reason": f"unreachable: {type(e).__name__}"}
        self.provider_status = status
        self._apply_status()
        return status

    def _apply_status(self) -> None:
        for m in self.models.values():
            st = self.provider_status.get(m.provider)
            if st is not None and not st["ok"]:
                m.available, m.why_unavailable = False, st["reason"]
            else:
                m.available, m.why_unavailable = True, ""
            if m.available and not m.chat_compatible:
                m.available, m.why_unavailable = False, "This model does not support the chat-completions text request used by this app."
            if m.available and not m.price_known:
                m.available, m.why_unavailable = False, "Pricing unavailable; refresh the registry or configure explicit provider prices before spending."

    # ------------------------------------------------------------------ lookups
    def get(self, model_id: str) -> ModelInfo:
        m = self.models.get(model_id)
        if m:
            return m
        # unknown id: treat as an OpenRouter model with unknown price rather than crash
        return ModelInfo(model_id, model_id, model_id.split("/")[0].title(), "openrouter", True, False, False, 32768, 0.5, 1.5, 2, False, False,
                         available=False, why_unavailable="Unknown model or pricing; refresh the registry first.", api_id=model_id)

    def list(self, q: str = "", include_all: bool = True, provider: str = "") -> list[ModelInfo]:
        ql = q.lower()
        out = [m for m in self.models.values()
               if (include_all or m.featured) and (not provider or m.provider == provider)
               and (not ql or ql in f"{m.name} {m.company} {m.id}".lower())]
        out.sort(key=lambda m: (not m.featured, m.price_out, m.name))
        return out

    def fallbacks(self, model_id: str, need_tools: bool = False, need_vision: bool = False, exclude: set[str] | None = None) -> list[str]:
        """Next models to try after retries fail (C8): similar strength, capable, available, other provider first."""
        base = self.get(model_id)
        skip = (exclude or set()) | {model_id}
        cands = [m for m in self.models.values()
                 if m.featured and m.available and m.id not in skip and (m.tools or not need_tools) and (m.vision or not need_vision)]
        cands.sort(key=lambda m: (m.provider == base.provider, abs(m.tier - base.tier), m.price_out))
        return [m.id for m in cands[:4]]

    def strongest_within(self, per_call_budget: float, need_tools: bool = False) -> str:
        """Composer default (C14): the strongest available model whose typical call fits the budget."""
        cands = [m for m in self.models.values() if m.featured and m.available and (m.tools or not need_tools) and m.call_cost() <= max(per_call_budget, 0)]
        if not cands:
            from app.core.costmeter import BudgetExceeded
            minimum = min((m.call_cost() for m in self.models.values() if m.available and (m.tools or not need_tools)), default=0)
            raise BudgetExceeded(0, per_call_budget, minimum)
        cands.sort(key=lambda m: (-m.tier, m.price_out))
        return cands[0].id


registry = Registry()


def _optional_price(value) -> float | None:
    try:
        price = float(value) * 1e6
        return price if math.isfinite(price) and price >= 0 else None
    except (ValueError, TypeError):
        return None


def _configured_price(name: str) -> float | None:
    try:
        price = float(config.env(name))
        return price if math.isfinite(price) and price >= 0 else None
    except (ValueError, TypeError):
        return None


def _optional_fee(value) -> float | None:
    try:
        fee = float(value or 0)
        return fee if math.isfinite(fee) and fee >= 0 else None
    except (ValueError, TypeError):
        return None


def db_cache_ttl() -> str:
    from app.core import db
    return "1h" if db.get_setting("promptCacheTtl", "5m") == "1h" else "5m"
