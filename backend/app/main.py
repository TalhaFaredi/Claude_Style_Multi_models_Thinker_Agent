"""FastAPI app: wires the routes, CORS, log redaction and start-up (database, model list, provider check).

Run:  uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import asyncio
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import ROUTERS
from app import tools
from app.core import config, db
from app.core.privacy import install_log_redaction
from app.llm import close_client, registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    install_log_redaction()
    db.conn()
    await registry.load()
    await tools.refresh_availability()
    await registry.probe_providers()   # publish models only after their provider availability is known
    yield
    await close_client()


class TokenGate:
    """When APP_TOKEN is set, every /api route needs `Authorization: Bearer <token>`. Plain ASGI, so answer
    streams pass through untouched. Generated-file downloads stay reachable by their unguessable id (a link
    cannot send a header, and a token in a URL would land in logs)."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (scope["type"] == "http" and config.APP_TOKEN and scope["method"] != "OPTIONS" and path.startswith("/api/")
                and not (scope["method"] == "GET" and path.startswith("/api/artifacts/"))):
            given = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(given.encode(), config.APP_TOKEN.encode()):
                await JSONResponse({"detail": "This server needs its access token."}, status_code=401)(scope, receive, send)
                return
        await self.inner(scope, receive, send)


app = FastAPI(title="Multi-Mode Assistant API", version=config.APP_VERSION, lifespan=lifespan)
app.add_middleware(TokenGate)   # added before CORS, so CORS wraps it and a 401 still carries the CORS headers
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])
for r in ROUTERS:
    app.include_router(r)
