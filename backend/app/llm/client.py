"""One adapter for every model. Both providers speak OpenAI-style chat requests, so one function,
`complete()`, serves every model, mode and stage.

What one call does (spec Part 1, the Fallback Manager and Cost Meter):
  1. Budget Guard: price the worst case and refuse before spending if it would pass the budget
  2. send the request (streamed or not) with httpx
  3. on an error worth retrying (timeout, rate limit, 5xx) retry 2 times after a short wait (tenacity)
  4. still failing: switch to the next capable model, other provider first (C8)
  5. meter the real cost reported by the provider, and log the call (model, tokens, cost, time)

Privacy: OpenRouter is asked to use only providers that do not store or train on prompts
(`provider.data_collection = "deny"`), unless the user turns the "privateProviders" setting off.
"""
from __future__ import annotations

import asyncio
import json
import time
import math
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.core import db
from app.core.config import CALL_TIMEOUT_S, LIMITS, NVIDIA_KEY, NVIDIA_URL, OPENROUTER_KEY, OPENROUTER_URL
from app.core.costmeter import CostMeter
from app.core.privacy import redact
from app.core.tokens import estimate_messages
from app.llm.registry import ModelInfo, registry


class LLMError(Exception):
    def __init__(self, message: str, status: int = 0, retriable: bool = False, fatal: bool = False, *, usage: Usage | None = None,
                 billed_unknown: bool = False):
        super().__init__(redact(message))
        self.status, self.retriable, self.fatal = status, retriable, fatal
        self.usage, self.billed_unknown = usage, billed_unknown


@dataclass
class Usage:
    prompt: int = 0
    completion: int = 0
    cached: int = 0
    reasoning: int = 0
    cost: float = 0.0
    estimated: bool = False


@dataclass
class ChatResult:
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    reasoning: str = ""
    finish: str = ""


@dataclass
class CallContext:
    """Who is calling and where the cost goes."""
    meter: CostMeter | None = None
    chat_id: str | None = None
    run_id: str | None = None
    on_switch: Callable[[str, str], Awaitable[None] | None] | None = None
    on_notice: Callable[[str], Awaitable[None] | None] | None = None
    on_event: Callable[[dict], Awaitable[None] | None] | None = None
    label: str | None = None                # role/step label; copy the context for concurrent agents


# ------------------------------------------------------------------ HTTP client (shared, pooled)

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(CALL_TIMEOUT_S, connect=10.0), limits=httpx.Limits(max_connections=40))
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def private_providers() -> bool:
    return bool(db.get_setting("privateProviders", True))


def openrouter_privacy() -> dict:
    """Request field that keeps prompts away from providers that log or train on them."""
    return {"provider": {"data_collection": "deny"}} if private_providers() else {}


def _endpoint(info: ModelInfo) -> tuple[str, dict]:
    if info.provider == "nvidia":
        return NVIDIA_URL, {"Authorization": f"Bearer {NVIDIA_KEY}"}
    return OPENROUTER_URL, {"Authorization": f"Bearer {OPENROUTER_KEY}", "X-Title": "Multi-Mode Assistant"}


# ------------------------------------------------------------------ request and response shapes

def _prepare_messages(info: ModelInfo, messages: list[dict]) -> list[dict]:
    """Anthropic models need an explicit cache marker on the stable prefix to get cheap cached reads."""
    if not info.id.startswith("anthropic/") or not messages or messages[0].get("role") != "system":
        return messages
    first = messages[0]
    if isinstance(first.get("content"), str):
        ttl = "1h" if db.get_setting("promptCacheTtl", "5m") == "1h" else "5m"
        first = {**first, "content": [{"type": "text", "text": first["content"], "cache_control": {"type": "ephemeral", "ttl": ttl}}]}
    return [first, *messages[1:]]


# Models that answered "reasoning is mandatory": learned at run time, so the failing request is sent once, not on every call.
_ALWAYS_REASONS: set[str] = set()
# (model, thinking level) pairs that spent the whole allowance on reasoning and returned no text: learned at run
# time, so the wasted call is paid once per server run instead of once per agent per question.
_NO_ANSWER_AT: set[tuple[str, str]] = set()


def _body(info: ModelInfo, messages: list[dict], *, stream: bool, tools, temperature, max_tokens, thinking: str) -> dict:
    body: dict = {"model": info.api_id or info.id, "messages": _prepare_messages(info, messages), "stream": stream}
    max_tokens = max_tokens or 1024
    effective_thinking = "low" if thinking == "off" and info.id in _ALWAYS_REASONS else thinking
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens:
        # Reasoning tokens count against max_tokens: leave room for them or the visible answer is empty.
        extra = {"low": 1024, "medium": 2048, "high": 4096}.get(effective_thinking, 0) if info.thinking else 0
        body["max_tokens"] = max_tokens + extra
    if tools and info.tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if info.provider == "openrouter":
        body["usage"] = {"include": True}
        body.update(openrouter_privacy())
        if info.thinking:
            body["reasoning"] = {"enabled": False} if effective_thinking == "off" else {"effort": effective_thinking}
    if stream:
        body["stream_options"] = {"include_usage": True}
    return body


def _usage_from(info: ModelInfo, u: dict | None) -> Usage:
    u = u or {}
    prompt, completion = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
    cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    reasoning = int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    written = int((u.get("prompt_tokens_details") or {}).get("cache_write_tokens") or 0)
    cost = u.get("cost")
    if cost is None:   # NVIDIA reports no cost: compute from the registry price
        cost = info.call_cost(prompt, completion, cached, written)
    cost = float(cost)
    if not math.isfinite(cost) or cost < 0 or min(prompt, completion, cached, reasoning) < 0:
        raise LLMError("Provider returned invalid usage", retriable=True, billed_unknown=True)
    return Usage(prompt, completion, cached, reasoning, cost, estimated=u.get("cost") is None)


def _returned_reasoning(message: dict) -> str:
    """Read provider-returned text/summary only; ignore encrypted reasoning payloads."""
    direct = message.get("reasoning")
    if isinstance(direct, str) and direct:
        return direct
    details = message.get("reasoning_details") or []
    if not isinstance(details, list):
        return ""
    parts = []
    for detail in details:
        if isinstance(detail, dict):
            value = detail.get("text") or detail.get("summary")
            if isinstance(value, str) and value:
                parts.append(value)
    return "\n".join(parts)


def _raise_for(status: int, body_text: str) -> None:
    msg = body_text[:300]
    try:
        j = json.loads(body_text)
        msg = (j.get("error") or {}).get("message") or j.get("detail") or msg
    except Exception:
        pass
    if status == 402:
        raise LLMError(f"Provider credits exhausted: {msg}", status)
    if status == 401:
        raise LLMError("Provider rejected the API key (401)", status)
    if status == 404 and "data policy" in str(msg).lower():
        raise LLMError("No private endpoint serves this model (privacy setting); trying another model", status)
    if status in (408, 409, 425, 429) or status >= 500:
        raise LLMError(f"HTTP {status}: {msg}", status, retriable=True)
    raise LLMError(f"HTTP {status}: {msg}", status)


async def _maybe(x):
    if asyncio.iscoroutine(x):
        await x


async def _read_json(info: ModelInfo, body: dict) -> ChatResult:
    base, headers = _endpoint(info)
    r = await client().post(f"{base}/chat/completions", headers=headers, json=body)
    if r.status_code != 200:
        _raise_for(r.status_code, r.text)
    try:
        j = r.json()
    except ValueError as e:
        raise LLMError("Provider returned invalid JSON", retriable=True, billed_unknown=True) from e
    if j.get("error"):
        raise LLMError(str(j["error"].get("message", j["error"]))[:300], retriable=True,
                       usage=_usage_for(info, body, j.get("usage")), billed_unknown=not bool(j.get("usage")))
    if not j.get("choices"):
        raise LLMError("Provider returned no answer choice", retriable=True, billed_unknown=True)
    ch = j["choices"][0]
    msg = ch.get("message") or {}
    tool_calls = [{"id": t.get("id"), "name": t["function"]["name"], "arguments": t["function"].get("arguments") or "{}"} for t in (msg.get("tool_calls") or [])]
    return ChatResult(text=msg.get("content") or "", tool_calls=tool_calls, usage=_usage_for(info, body, j.get("usage")), model=info.id,
                      reasoning=_returned_reasoning(msg), finish=ch.get("finish_reason") or "")


async def _read_stream(info: ModelInfo, body: dict, on_text, on_reasoning) -> ChatResult:
    base, headers = _endpoint(info)
    res = ChatResult(model=info.id)
    tool_acc: dict[int, dict] = {}
    raw_usage: dict | None = None
    async with client().stream("POST", f"{base}/chat/completions", headers=headers, json=body) as r:
        if r.status_code != 200:
            _raise_for(r.status_code, (await r.aread()).decode("utf-8", "replace"))
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue   # SSE comments such as ": OPENROUTER PROCESSING"
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                d = json.loads(data)
            except ValueError:
                continue
            if d.get("error"):
                raise LLMError(str(d["error"].get("message", d["error"]))[:300], retriable=True,
                               usage=_usage_for(info, body, d.get("usage") or raw_usage), billed_unknown=raw_usage is None)
            raw_usage = d.get("usage") or raw_usage
            for ch in d.get("choices") or []:
                delta = ch.get("delta") or {}
                res.finish = ch.get("finish_reason") or res.finish
                returned = _returned_reasoning(delta)
                if returned:
                    res.reasoning += returned
                    if on_reasoning:
                        await _maybe(on_reasoning(returned))
                if delta.get("content"):
                    res.text += delta["content"]
                    if on_text:
                        await _maybe(on_text(delta["content"]))
                for tc in delta.get("tool_calls") or []:
                    slot = tool_acc.setdefault(tc.get("index", 0), {"id": None, "name": "", "arguments": ""})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["arguments"] += fn.get("arguments") or ""
    res.tool_calls = [tool_acc[k] for k in sorted(tool_acc)]
    res.usage = _usage_for(info, body, raw_usage)
    if not res.finish:
        raise LLMError("Provider stream ended without a completion marker", retriable=True, usage=res.usage, billed_unknown=raw_usage is None)
    return res


def _prompt_bound(info: ModelInfo, body: dict) -> int:
    """A conservative UTF-8/token bound, including function schemas and message framing."""
    count = 32
    for msg in body.get("messages", []):
        count += 32
        content = msg.get("content")
        if isinstance(content, str):
            count += len(content.encode("utf-8"))
        elif isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    count += len(str(block.get("text", "")).encode("utf-8"))
                elif block.get("type") == "image_url":
                    count += info.context  # image tokenization is provider-specific; reserve its input window
        if msg.get("tool_calls"):
            count += len(json.dumps(msg["tool_calls"], ensure_ascii=False).encode("utf-8"))
    if body.get("tools"):
        count += len(json.dumps(body["tools"], ensure_ascii=False).encode("utf-8"))
    return min(info.context, max(count, estimate_messages(body.get("messages", []))))


def _maximum_cost(info: ModelInfo, body: dict) -> float:
    tin, tout = _prompt_bound(info, body), int(body.get("max_tokens") or 1024)
    if info.id.startswith("anthropic/"):
        # Reserve a cache write, including 1h TTL, even if this particular request hits a cache.
        multiplier = 2 if db.get_setting("promptCacheTtl", "5m") == "1h" else 1.25
        input_rate = max(info.price_in * multiplier, info.price_cache_write or 0)
        return (tin * input_rate + tout * info.price_out) / 1e6 + info.price_request
    return info.call_cost(tin, tout)


def _estimated_usage(info: ModelInfo, body: dict) -> Usage:
    """Missing upstream usage is unknown, never a fictional free generation."""
    return Usage(prompt=_prompt_bound(info, body), completion=int(body.get("max_tokens") or 1024),
                 cost=_maximum_cost(info, body), estimated=True)


def _usage_for(info: ModelInfo, body: dict, raw: dict | None) -> Usage:
    if isinstance(raw, dict) and raw.get("prompt_tokens") is not None and raw.get("completion_tokens") is not None:
        return _usage_from(info, raw)
    estimated = _estimated_usage(info, body)
    if isinstance(raw, dict) and raw.get("cost") is not None:
        reported = float(raw["cost"])
        if not math.isfinite(reported) or reported < 0:
            raise LLMError("Provider returned invalid usage", retriable=True, billed_unknown=True)
        estimated.cost = reported
    return estimated


async def _call_once(info: ModelInfo, body: dict, stream: bool, on_text, on_reasoning) -> ChatResult:
    try:
        return await (_read_stream(info, body, on_text, on_reasoning) if stream else _read_json(info, body))
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise LLMError(f"network: {type(e).__name__}", retriable=True, billed_unknown=True) from e
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        raise LLMError(f"Malformed provider response ({type(e).__name__})", retriable=True, billed_unknown=True) from e


def _log(ctx: CallContext, stage: str, info: ModelInfo, usage: Usage | None, ms: int, err: str | None) -> None:
    """One row per call: the books. No prompt or answer text is stored here."""
    u = usage or Usage()
    db.run("INSERT INTO calls(ts,run_id,chat_id,stage,provider,model,in_tokens,out_tokens,cached_tokens,reasoning_tokens,cost,ms,ok,error,usage_estimated,completed) "
           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (db.now(), ctx.run_id, ctx.chat_id, stage, info.provider, info.id, u.prompt, u.completion, u.cached, u.reasoning, u.cost, ms,
            0 if err else 1, redact(err)[:300] if err else None, int(u.estimated), 0 if err else 1))


async def _call_events(ctx: CallContext, stage: str, info: ModelInfo, usage: Usage, *, ok: bool,
                       reasoning: str = "", requested: bool = False) -> None:
    """Send billed usage and only provider-exposed reasoning; never send prompt text or keys."""
    if not ctx.on_event:
        return
    await _maybe(ctx.on_event({
        "type": "call_usage", "stage": stage, "model": info.id, "provider": info.provider, "label": ctx.label,
        "inTokens": usage.prompt, "outTokens": usage.completion, "reasoningTokens": usage.reasoning,
        "usd": round(usage.cost, 8), "estimated": usage.estimated, "ok": ok,
    }))
    if ok:
        # This is an excerpt of returned provider text, not the model's unexposed internal thoughts.
        notes = [part.strip()[:160] for part in re.split(r"(?<=[.!?])\s+|\n+", reasoning[:1600]) if part.strip()][:5]
        if not (requested or notes):
            return   # router, checker and judge calls never ask for thinking: no "notes unavailable" row for them
        await _maybe(ctx.on_event({"type": "model_thinking", "stage": stage, "model": info.id,
                                   "label": ctx.label, "available": bool(notes), "notes": notes}))


def _retriable(e: BaseException) -> bool:
    return isinstance(e, LLMError) and e.retriable


async def _call_with_retries(info: ModelInfo, body: dict, stream: bool, on_text, on_reasoning, ctx: CallContext, stage: str,
                             on_reset=None, max_retries: int | None = None) -> ChatResult:
    """C8, first half: retry 2 times after a short, growing wait, only for errors worth retrying."""
    retries = LIMITS.max_retries if max_retries is None else max(0, min(int(max_retries), LIMITS.max_retries))
    retrying = AsyncRetrying(retry=retry_if_exception(_retriable), stop=stop_after_attempt(retries + 1),
                             wait=wait_exponential(multiplier=0.6, max=4), reraise=True)
    async for attempt in retrying:
        with attempt:
            t0 = time.perf_counter()
            booking = ctx.meter.reserve(_maximum_cost(info, body)) if ctx.meter else None
            buffered_text: list[str] = []
            buffered_reasoning: list[str] = []
            text_cb = on_text if on_reset else buffered_text.append
            reason_cb = on_reasoning if on_reset else buffered_reasoning.append
            try:
                res = await _call_once(info, body, stream, text_cb if on_text else None, reason_cb if on_reasoning else None)
            except LLMError as e:
                usage = e.usage or (_estimated_usage(info, body) if e.billed_unknown else Usage())
                if booking:
                    booking.settle(stage, usage.cost, usage.prompt, usage.completion, usage.cached, estimated=usage.estimated)
                _log(ctx, stage, info, usage, int((time.perf_counter() - t0) * 1000), str(e))
                await _call_events(ctx, stage, info, usage, ok=False)
                if stream and on_reset:
                    await _maybe(on_reset())
                if e.status == 400 and body.get("reasoning", {}).get("enabled") is False and "reasoning" in str(e).lower():
                    # Some models require reasoning. Reserve its allowance again before the retry.
                    body["reasoning"] = {"effort": "low"}
                    body["max_tokens"] += 1024
                    _ALWAYS_REASONS.add(info.id)
                    if ctx.on_notice:
                        await _maybe(ctx.on_notice("This model requires reasoning. Using its lowest thinking level within the approved budget."))
                    e.retriable = True
                raise
            except BaseException as e:
                # Cancellation can arrive after remote generation has started. Conservatively account for it.
                usage = _estimated_usage(info, body)
                if booking:
                    booking.settle(stage, usage.cost, usage.prompt, usage.completion, usage.cached, estimated=True)
                _log(ctx, stage, info, usage, int((time.perf_counter() - t0) * 1000), type(e).__name__)
                await _call_events(ctx, stage, info, usage, ok=False)
                raise
            if booking:
                booking.settle(stage, res.usage.cost, res.usage.prompt, res.usage.completion, res.usage.cached, estimated=res.usage.estimated)
            _log(ctx, stage, info, res.usage, int((time.perf_counter() - t0) * 1000), None)
            asked = isinstance(body.get("reasoning"), dict) and body["reasoning"].get("enabled") is not False
            await _call_events(ctx, stage, info, res.usage, ok=True, reasoning=res.reasoning, requested=asked)
            if not on_reset:
                for chunk in buffered_reasoning:
                    await _maybe(on_reasoning(chunk))
                for chunk in buffered_text:
                    await _maybe(on_text(chunk))
            return res
    raise LLMError("unreachable")


def _reasoning_ate_the_answer(info: ModelInfo, body: dict, res: ChatResult) -> bool:
    """True when reasoning was on and the reply has no visible text and no tool call."""
    reasoning_on = info.thinking and body.get("reasoning", {}).get("enabled") is not False
    return bool(reasoning_on and not res.text.strip() and not res.tool_calls)


async def complete(
    model: str, messages: list[dict], *, stage: str, ctx: CallContext | None = None, tools: list[dict] | None = None,
    temperature: float | None = None, max_tokens: int | None = None, thinking: str = "off", stream: bool = False,
    on_text=None, on_reasoning=None, on_reset=None, need_vision: bool = False, allow_fallback: bool = True, exclude: set[str] | None = None,
    max_retries: int | None = None,
) -> ChatResult:
    """Run one model call with budget guard, retry, fallback, metering and logging."""
    ctx = ctx or CallContext()
    chain = [model] + (registry.fallbacks(model, need_tools=bool(tools), need_vision=need_vision, exclude=exclude) if allow_fallback else [])
    last_err: LLMError | None = None
    failed_providers: set[str] = set()

    for pos, mid in enumerate(chain):
        info = registry.get(mid)
        if not info.available or info.provider in failed_providers:
            last_err = LLMError(f"{info.name} unavailable: {info.why_unavailable}")
            continue
        if need_vision and not info.vision:
            continue
        if pos > 0 and ctx.on_switch:
            await _maybe(ctx.on_switch(model, mid))
        if thinking == "off" and info.id in _ALWAYS_REASONS and ctx.on_notice:
            await _maybe(ctx.on_notice("This model requires reasoning. Using its lowest thinking level within the approved budget."))
        effort = "off" if (info.id, thinking) in _NO_ANSWER_AT else thinking
        body = _body(info, messages, stream=stream, tools=tools, temperature=temperature, max_tokens=max_tokens, thinking=effort)
        try:
            res = await _call_with_retries(info, body, stream, on_text if stream else None, on_reasoning if stream else None, ctx, stage, on_reset, max_retries)
        except LLMError as e:
            if e.fatal:
                raise
            if e.status in (401, 402, 403):
                failed_providers.add(info.provider)
            last_err = e   # C8, second half: the next model or the other provider
            continue
        if _reasoning_ate_the_answer(info, body, res):
            # Measured live: qwen3.7-flash at "low" spent its whole allowance on reasoning and returned no text.
            # Ask once more without reasoning; a model that cannot turn reasoning off moves on to the next model.
            if info.id in _ALWAYS_REASONS:
                last_err = LLMError(f"{info.name} returned no answer: reasoning used the whole token allowance")
                continue
            if res.finish == "length" or res.usage.reasoning:
                _NO_ANSWER_AT.add((info.id, thinking))
            if ctx.on_notice:
                await _maybe(ctx.on_notice("The model used its whole allowance on thinking; asking again without thinking."))
            body = _body(info, messages, stream=stream, tools=tools, temperature=temperature, max_tokens=max_tokens, thinking="off")
            try:
                res = await _call_with_retries(info, body, stream, on_text if stream else None, on_reasoning if stream else None, ctx, stage, on_reset, max_retries)
            except LLMError as e:
                if e.fatal:
                    raise
                last_err = e
                continue
        res.model = info.id
        return res
    raise last_err or LLMError("No available model for this request")
