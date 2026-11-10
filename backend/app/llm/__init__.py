"""Model access: the Model Registry and the one adapter every stage uses.

Always call models as `llm.complete(...)` / `llm.ask_json(...)` (through this package), never by
importing the function directly. That keeps one patch point for the offline tests.
"""
from app.llm.client import CallContext, ChatResult, LLMError, Usage, client, close_client, complete, openrouter_privacy
from app.llm.jsonutil import ask_json, parse_json
from app.llm.registry import QUALITY_PRESETS, ModelInfo, registry

__all__ = ["CallContext", "ChatResult", "LLMError", "Usage", "client", "close_client", "complete", "openrouter_privacy",
           "ask_json", "parse_json", "QUALITY_PRESETS", "ModelInfo", "registry"]
