"""HTTP routes, one module per area. Events stream over Server-Sent Events.

    meta.py     /health, /api/config, models, settings, usage, skills, tools, estimate
    chats.py    chats, context meter, ledger, Summarize now, export, import
    files.py    upload, read, detach, generated-file download
    runs.py     start a run (SSE), approve, edit, stop, rating
    memory.py   long-term facts
"""
from app.api import auth, chats, files, memory, meta, runs

ROUTERS = [meta.router, auth.router, chats.router, files.router, runs.router, memory.router]
