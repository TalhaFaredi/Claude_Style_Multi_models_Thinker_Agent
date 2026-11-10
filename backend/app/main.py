"""FastAPI app: wires the routes, CORS, log redaction and start-up (database, model list, provider check).

Run:  uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


app = FastAPI(title="Multi-Mode Assistant API", version=config.APP_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])
for r in ROUTERS:
    app.include_router(r)
