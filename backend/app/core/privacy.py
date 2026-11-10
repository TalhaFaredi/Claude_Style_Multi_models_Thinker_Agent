"""No data leakage: one place for every rule that keeps secrets and private data inside the app.

  * redact()            removes this server's provider keys and key-shaped strings from any text
  * RedactingFilter     applied to every log handler, so a key can never reach a log file or console
  * safe_message()      turns an exception into a short, redacted message that is safe to show a user
  * is_fingerprint() / is_hex_id()   strict ID checks, so a crafted ID can never become a file path

Other leakage rules live next to the code they protect and point back here:
  - OpenRouter requests ask for providers that do not store or train on prompts (app/llm/client.py)
  - deleting a chat removes its files, readings, indexes and generated files (app/memory/archive.py)
  - temporary chats neither read nor write long-term memory (app/memory/settings.py)
  - the web page tool only opens links that search returned in this run, and never a private address
    (app/tools/read_webpage.py)
  - text from files, web pages and imports is always wrapped as DATA, never obeyed (app/prompts/)
"""
from __future__ import annotations

import logging
import re

from app.core import config

_KEY_SHAPES = re.compile(r"(sk-or-v1-[A-Za-z0-9]{16,}|nvapi-[A-Za-z0-9_\-]{16,}|sk-(?:proj-)?[A-Za-z0-9_\-]{32,}|Bearer\s+[A-Za-z0-9._\-]{20,})")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_HEX_ID = re.compile(r"^[0-9a-f]{8,64}$")


def _own_keys() -> list[str]:
    return [k for k in (config.OPENROUTER_KEY, config.NVIDIA_KEY) if k and len(k) > 12]


def redact(text: str) -> str:
    """Remove this server's keys and anything shaped like an API key."""
    if not text:
        return text
    for key in _own_keys():
        text = text.replace(key, "[redacted]")
    return _KEY_SHAPES.sub("[redacted]", text)


def redact_flag(text: str) -> tuple[str, bool]:
    new = redact(text)
    return new, new != text


def safe_message(e: BaseException, limit: int = 200) -> str:
    return redact(str(e))[:limit]


def is_fingerprint(value: str) -> bool:
    return bool(_FINGERPRINT.match(value or ""))


def is_hex_id(value: str) -> bool:
    return bool(_HEX_ID.match(value or ""))


class RedactingFilter(logging.Filter):
    """Rewrites every log record so keys never leave the process, even inside tracebacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        clean = redact(msg)
        if record.exc_info:
            clean += "\n" + redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info, record.exc_text = None, None
        record.msg, record.args = clean, None
        return True


def install_log_redaction() -> None:
    """Attach the filter to the root logger and to uvicorn's loggers (they have their own handlers)."""
    f = RedactingFilter()
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "fastapi"):
        lg = logging.getLogger(name)
        lg.addFilter(f)
        for h in lg.handlers:
            h.addFilter(f)
    # httpx logs every request URL at INFO; URLs carry no keys, but they can carry user queries
    logging.getLogger("httpx").setLevel(logging.WARNING)
