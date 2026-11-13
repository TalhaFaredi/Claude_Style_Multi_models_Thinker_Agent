"""Configuration: .env loading, the fixed safety limits from the spec, and tunable defaults.

Secrets are read from the repo-root `.env` (or real environment variables). They are never logged,
returned by the API, or written to disk by this app (see app/core/privacy.py).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]          # backend/app
BACKEND_DIR = APP_DIR.parent                           # backend
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BACKEND_DIR / "data"))
PROMPTS_DIR = APP_DIR / "prompts"
SKILLS_DIR = APP_DIR / "skills"


def _parse_env_file(path: Path) -> dict[str, str]:
    """Tolerant .env parser: `key = value`, quotes, comments, BOM, spaces around '='."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"\s*([^#=\s]+)\s*=\s*(.*?)\s*$", line)
        if m:
            out[m.group(1)] = m.group(2).strip("'\"")
    return out


_ENV = {**_parse_env_file(REPO_ROOT / ".env"), **_parse_env_file(BACKEND_DIR / ".env")}


def env(*names: str, default: str = "") -> str:
    """First non-empty value among real env vars and .env entries (case-insensitive names)."""
    for n in names:
        for key in (n, n.upper(), n.lower()):
            v = os.environ.get(key) or _ENV.get(key)
            if v:
                return v
    return default


OPENROUTER_KEY = env("OPENROUTER_API_KEY", "open_router_api")
NVIDIA_KEY = env("NVIDIA_API_KEY", "nvidian_key")

OPENROUTER_URL = "https://openrouter.ai/api/v1"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1"


@dataclass(frozen=True)
class Limits:
    """Fixed safety limits (spec Part 1 section 8). The UI cannot raise them."""
    min_agents: int = 2
    max_agents: int = 5
    min_rounds: int = 1
    max_rounds: int = 3
    max_tool_calls: int = 10
    max_retries: int = 2          # per call or step
    max_replans: int = 2
    max_plan_steps: int = 20
    max_parallel_steps: int = 3


LIMITS = Limits()

# Context window (spec Part 2 sections 6 and 7)
ANSWER_RESERVE = 0.15             # share of the window kept free for the answer
FILES_BUDGET = 0.35               # files up to 35% of the window: full text, else search
MEMORY_BUDGET = 0.10
SUMMARY_BUDGET = 0.05
SKILLS_BUDGET = 0.05              # skills share the "rules, tools: up to 5%" part
LEVEL_NOTICE, LEVEL_ALARM, LEVEL_COMPACT = 70, 85, 95
KEEP_LAST_TURNS = 10              # never compacted
CHUNK_TOKENS = 800
TOP_CHUNKS = 8

# Working window cap. Every turn re-sends the whole window, so a big window costs real money.
# 32k keeps testing cheap and makes the 70/85/95% levels reachable. Raise it in Settings.
DEFAULT_WINDOW_CAP = int(env("WINDOW_CAP_TOKENS", default="32000"))

# Cheap models for the "small model" jobs in the spec (router, judge, checker, memory writer, cards).
UTILITY_MODEL = env("UTILITY_MODEL", default="meta-llama/llama-3.1-8b-instruct")
# The Checker decides what reaches the user, so it gets a slightly stronger cheap model. Measured Nov 10, 2026 on
# file-grounded and plain answers (21 verdicts each): llama-3.1-8b 18/21 (rejected a correct file answer 2 of 3 times),
# qwen3.7-flash 21/21 at about $0.00002 per check.
CHECKER_MODEL = env("CHECKER_MODEL", default="qwen/qwen3.7-flash")
WRITER_MODEL = env("WRITER_MODEL", default="qwen/qwen3.7-flash")
VISION_MODEL = env("VISION_MODEL", default="qwen/qwen3.7-flash")
EMBED_MODEL = env("EMBED_MODEL", default="openai/text-embedding-3-small")

# Run limits
RUN_TIMEOUT_S = int(env("RUN_TIMEOUT_S", default="300"))
PLANNER_TIMEOUT_S = int(env("PLANNER_TIMEOUT_S", default="900"))
CALL_TIMEOUT_S = float(env("CALL_TIMEOUT_S", default="90"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_IMPORT_BYTES = int(float(env("MAX_IMPORT_MB", default="200")) * 1024 * 1024)

# Input check: a small helper model screens each message for safety (and, before a Thinker or Planner run, asks one
# question when the goal is unknown). It never answers in place of the selected model. 0 = skip the helper call.
INPUT_CHECK = env("INPUT_CHECK", default="1") != "0"

# Show the draft while it streams (best UX); the Checker still runs afterwards and can replace it.
# Set STREAM_BEFORE_CHECK=0 to hold the draft until it passes (strict "nothing before the Checker").
STREAM_BEFORE_CHECK = env("STREAM_BEFORE_CHECK", default="1") != "0"
CHECK_ANSWERS = env("CHECK_ANSWERS", default="1") != "0"

# Access token for every /api route. Empty = open, which is only safe on 127.0.0.1. Set it before the server is
# reachable from another machine: anyone who can call the API spends the provider credit and reads the chats.
APP_TOKEN = env("APP_TOKEN")

CORS_ORIGINS = [o.strip() for o in env("CORS_ORIGINS", default="http://localhost:3000,http://localhost:3123,http://127.0.0.1:3000").split(",") if o.strip()]

# ----------------------------------------------------------------------------------------------------------------
# Production / multi-user settings
# ----------------------------------------------------------------------------------------------------------------
def _flag(name: str, default: str) -> bool:
    return env(name, default=default).strip().lower() not in ("0", "false", "no", "off", "")


def _num(name: str, default: float) -> float:
    try:
        return float(env(name, default=str(default)))
    except ValueError:
        return default


APP_ENV = env("APP_ENV", default="development").strip().lower()
PRODUCTION = APP_ENV == "production"

# Accounts. When off, the API is single-user and open (local use only; refused in production).
AUTH_REQUIRED = _flag("AUTH_REQUIRED", "1")
# Public address of the site, e.g. https://assistant.example.com. Used for the CSRF origin check and e-mailed links.
PUBLIC_URL = env("PUBLIC_URL").rstrip("/")
COOKIE_SECURE = _flag("COOKIE_SECURE", "1" if PRODUCTION else "0")
SESSION_DAYS = int(_num("SESSION_DAYS", 30))
ALLOW_SIGNUP = _flag("ALLOW_SIGNUP", "1")
INVITE_CODE = env("INVITE_CODE")                      # when set, signing up needs this code
ADMIN_EMAILS = {e.strip().lower() for e in env("ADMIN_EMAILS").split(",") if e.strip()}   # become admins on sign-up
MIN_PASSWORD_LENGTH = 10

# Spending. Every user shares the operator's provider account, so these caps are enforced on the server.
DEFAULT_USER_MONTHLY_USD = _num("DEFAULT_USER_MONTHLY_USD", 2.0)   # per user per calendar month (admin can override per user)
MAX_RUN_USD = _num("MAX_RUN_USD", 1.0)                             # ceiling for one question, whatever the client sends
GLOBAL_MONTHLY_USD = _num("GLOBAL_MONTHLY_USD", 0.0)               # all users together; 0 = no global cap

# Load limits (one server process; runs live in memory).
MAX_CONCURRENT_RUNS = int(_num("MAX_CONCURRENT_RUNS", 8))
MAX_RUNS_PER_USER = int(_num("MAX_RUNS_PER_USER", 2))
MAX_USER_STORAGE_MB = int(_num("MAX_USER_STORAGE_MB", 500))
RUNS_PER_MINUTE = int(_num("RUNS_PER_MINUTE", 20))
AUTH_ATTEMPTS_PER_15_MIN = int(_num("AUTH_ATTEMPTS_PER_15_MIN", 10))

# Password-reset e-mail (optional). Without SMTP, an admin resets passwords with `python -m app.admin`.
SMTP_HOST = env("SMTP_HOST")
SMTP_PORT = int(_num("SMTP_PORT", 587))
SMTP_USER = env("SMTP_USER")
SMTP_PASSWORD = env("SMTP_PASSWORD")
SMTP_STARTTLS = _flag("SMTP_STARTTLS", "1")
MAIL_FROM = env("MAIL_FROM", default=SMTP_USER)

# Names shown on the legal pages and in e-mails.
SITE_NAME = env("SITE_NAME", default="Multi-Mode Assistant")
CONTACT_EMAIL = env("CONTACT_EMAIL")

APP_VERSION = "0.3.0"
EXPORT_FORMAT_VERSION = 1
PARSE_VERSION = 1   # bump to invalidate the Parse Cache when readers change
