"""Plain ASGI middleware (not Starlette's BaseHTTPMiddleware), so streamed answers pass through untouched and the
ContextVars set here are visible to the route handlers and to every task they start."""
from __future__ import annotations

from http.cookies import CookieError, SimpleCookie

from fastapi.responses import JSONResponse

from app.core import auth, config, db

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Reachable without a session. Each of these checks what it needs itself.
PUBLIC_PATHS = frozenset({
    "/api/auth/config", "/api/auth/signup", "/api/auth/login", "/api/auth/logout", "/api/auth/me", "/api/auth/forgot", "/api/auth/reset",
})


def allowed_origins() -> set[str]:
    origins = {o.rstrip("/") for o in config.CORS_ORIGINS}
    if config.PUBLIC_URL:
        origins.add(config.PUBLIC_URL)
    return origins


def read_cookie(raw: bytes | None, name: str) -> str | None:
    if not raw:
        return None
    try:
        jar = SimpleCookie()
        jar.load(raw.decode("latin-1"))
    except CookieError:
        return None
    morsel = jar.get(name)
    return morsel.value if morsel else None


class AuthMiddleware:
    """For every /api request: CSRF origin check, then (when accounts are on) the session cookie decides who the user is.
    The user's id is set for the whole request, and every query in the app filters by it."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/"):
            await self.inner(scope, receive, send)
            return
        headers = dict(scope["headers"])
        method = scope["method"]

        # CSRF: browsers always say where a state-changing request came from. A foreign page cannot forge this header.
        origin = headers.get(b"origin", b"").decode("latin-1").rstrip("/")
        if method in UNSAFE and origin and origin not in allowed_origins():
            await JSONResponse({"detail": "Cross-site request refused."}, status_code=403)(scope, receive, send)
            return

        if not config.AUTH_REQUIRED:
            await self.inner(scope, receive, send)
            return

        token = read_cookie(headers.get(b"cookie"), auth.SESSION_COOKIE)
        user = auth.session_user(token)
        if user is None and path not in PUBLIC_PATHS:
            await JSONResponse({"detail": "Please sign in to continue.", "code": "auth_required"}, status_code=401)(scope, receive, send)
            return
        scope.setdefault("state", {})["session_token"] = token
        ctx_user = db.set_uid(user.id) if user else None
        ctx_auth = auth.set_current(user)
        try:
            await self.inner(scope, receive, send)
        finally:
            auth.reset_current(ctx_auth)
            if ctx_user is not None:
                db.reset_uid(ctx_user)
