"""User settings with safe defaults (spec Part 3 section 8). Only known keys are stored; values are clamped."""
from __future__ import annotations

import json
import math

from app.core import config, db

DEFAULT_SETTINGS = {
    "reader": "auto", "askLimit": 0.5, "monthBudget": 5.0, "longMemory": True, "autoCompact": True, "tempChat": False,
    "chartDescriptions": True, "keepPageImages": True, "windowCap": config.DEFAULT_WINDOW_CAP, "embeddings": True,
    "privateProviders": True,   # OpenRouter: only providers that do not store or train on prompts
    "promptCacheTtl": "5m",
}


def get_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    for k in DEFAULT_SETTINGS:
        v = db.get_setting(k)
        if v is not None:
            s[k] = v
    if config.AUTH_REQUIRED:   # the operator's caps always win over what a user saved
        from app.core import usage
        s["monthBudget"] = min(float(s["monthBudget"]), usage.month_cap())
        s["askLimit"] = min(float(s["askLimit"]), config.MAX_RUN_USD)
    return s


def update_settings(patch: dict) -> dict:
    validated = {}
    for k, v in patch.items():
        if k not in DEFAULT_SETTINGS:
            continue
        if k == "windowCap":
            try:
                v = max(4000, min(int(v), 1_000_000))
            except (TypeError, ValueError, OverflowError):
                raise ValueError("windowCap must be a finite integer")
        elif k == "promptCacheTtl":
            if v not in ("5m", "1h"):
                raise ValueError("promptCacheTtl must be 5m or 1h")
        elif k == "reader":
            if v not in ("auto", "text", "local", "api", "vision"):
                raise ValueError("Unknown file reader")
        elif k in ("askLimit", "monthBudget"):
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k} must be a finite number")
            if not math.isfinite(v):
                raise ValueError(f"{k} must be a finite number")
            v = max(0.0, min(1000.0, v))
            if config.AUTH_REQUIRED:
                from app.core import usage
                v = min(v, usage.month_cap() if k == "monthBudget" else config.MAX_RUN_USD)
        elif isinstance(DEFAULT_SETTINGS[k], bool):
            if not isinstance(v, bool):
                raise ValueError(f"{k} must be true or false")
        validated[k] = v
    with db.tx() as conn:
        for key, value in validated.items():
            conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (db.setting_key(key), json.dumps(value)))
    return get_settings()


def long_memory_on(chat: dict | None) -> bool:
    """C41: a temporary chat, or long-term memory switched off, neither reads nor writes long-term facts."""
    s = get_settings()
    return bool(chat) and not chat.get("temp") and bool(s["longMemory"]) and not s["tempChat"]
