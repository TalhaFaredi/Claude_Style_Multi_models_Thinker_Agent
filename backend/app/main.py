"""FastAPI app: wires the routes, CORS, accounts, log redaction and start-up (database, model list, provider check).

Run (development):  uvicorn app.main:app --host 127.0.0.1 --port 8000
Run (production):   see DEPLOYMENT.md  (one process: live runs are kept in memory, so do not add --workers)
"""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import ROUTERS
from app import tools
from app.core import config, db
from app.core.errors import UnknownChat
from app.core.middleware import AuthMiddleware
from app.core.privacy import install_log_redaction
from app.core.usage import SpendBlocked
from app.llm import close_client, registry

log = logging.getLogger("app")


def startup_problems() -> tuple[list[str], list[str]]:
    """(fatal, warnings) for the running configuration. In production a fatal problem stops the server from starting."""
    fatal, warn = [], []
    if config.PRODUCTION:
        if not config.AUTH_REQUIRED:
            fatal.append("AUTH_REQUIRED=0 is not allowed in production: anyone could read every chat and spend your provider credit.")
        if not config.COOKIE_SECURE:
            fatal.append("COOKIE_SECURE must be on in production (serve the site over HTTPS).")
        if not config.PUBLIC_URL.startswith("https://"):
            fatal.append("PUBLIC_URL must be your site's https:// address in production (it is used for the CSRF origin check).")
        if not config.ADMIN_EMAILS:
            warn.append("ADMIN_EMAILS is empty: nobody can open the admin page until you create an admin with `python -m app.admin create-user --admin`.")
        if config.GLOBAL_MONTHLY_USD <= 0:
            warn.append("GLOBAL_MONTHLY_USD is 0 (no overall spending cap). Set one so a bug or abuse cannot drain your provider account.")
        if not config.SMTP_HOST:
            warn.append("SMTP is not configured: password-reset e-mails are off. Reset passwords with `python -m app.admin set-password`.")
    if not config.OPENROUTER_KEY:
        warn.append("OPENROUTER_API_KEY is not set: no model can answer.")
    return fatal, warn


@asynccontextmanager
async def lifespan(app: FastAPI):
    install_log_redaction()
    fatal, warn = startup_problems()
    for w in warn:
        log.warning("config: %s", w)
    if fatal:
        raise RuntimeError("Refusing to start: " + " ".join(fatal))
    db.conn()
    await registry.load()
    await tools.refresh_availability()
    await registry.probe_providers()   # publish models only after their provider availability is known
    yield
    await close_client()


class TokenGate:
    """Single-user mode only (AUTH_REQUIRED=0): when APP_TOKEN is set, every /api route needs `Authorization: Bearer <token>`.
    Plain ASGI, so answer streams pass through untouched. Generated-file downloads stay reachable by their unguessable id
    (a link cannot send a header, and a token in a URL would land in logs). With accounts on, the session cookie replaces this."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (scope["type"] == "http" and not config.AUTH_REQUIRED and config.APP_TOKEN and scope["method"] != "OPTIONS" and path.startswith("/api/")
                and not (scope["method"] == "GET" and path.startswith("/api/artifacts/"))):
            given = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(given.encode(), config.APP_TOKEN.encode()):
                await JSONResponse({"detail": "This server needs its access token."}, status_code=401)(scope, receive, send)
                return
        await self.inner(scope, receive, send)


# The interactive API docs list every route; keep them off the public internet.
app = FastAPI(title="Multi-Mode Assistant API", version=config.APP_VERSION, lifespan=lifespan,
              docs_url=None if config.PRODUCTION else "/docs", redoc_url=None, openapi_url=None if config.PRODUCTION else "/openapi.json")
app.add_middleware(AuthMiddleware)   # innermost: runs after CORS and the token gate
app.add_middleware(TokenGate)        # added before CORS, so CORS wraps it and a 401 still carries the CORS headers
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["Content-Disposition"])
for r in ROUTERS:
    app.include_router(r)


@app.exception_handler(UnknownChat)
async def unknown_chat(_: Request, __: UnknownChat):
    return JSONResponse({"detail": "Unknown chat"}, status_code=404)


@app.exception_handler(SpendBlocked)
async def spend_blocked(_: Request, e: SpendBlocked):
    return JSONResponse({"detail": str(e), "code": "allowance_used"}, status_code=402)
