"""Accounts: sign up, sign in/out, who am I, change password, reset password by e-mail, delete the account, and the
operator's admin endpoints."""
from __future__ import annotations

import asyncio
import hmac
import logging
import sqlite3

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app import memory
from app.core import auth, config, db, mail, usage
from app.core.auth import AuthError

router = APIRouter()
log = logging.getLogger("api.auth")


# ---------------------------------------------------------------------------------------------- helpers
def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(auth.SESSION_COOKIE, token, max_age=config.SESSION_DAYS * 86400, httponly=True, secure=config.COOKIE_SECURE,
                        samesite="lax", path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(auth.SESSION_COOKIE, path="/", httponly=True, secure=config.COOKIE_SECURE, samesite="lax")


def user_json(user: auth.User) -> dict:
    return {"id": user.id, "email": user.email, "isAdmin": user.is_admin, "monthCapUsd": round(usage.month_cap(), 4),
            "monthSpentUsd": round(usage.month_spent(), 6)}


def require_user() -> auth.User:
    user = auth.current_user() or (auth.LOCAL_USER if not config.AUTH_REQUIRED else None)
    if user is None:
        raise HTTPException(401, "Please sign in to continue.")
    return user


def require_admin() -> auth.User:
    user = require_user()
    if not user.is_admin:
        raise HTTPException(403, "Administrators only.")
    return user


def _too_many() -> HTTPException:
    return HTTPException(429, "Too many attempts. Please wait a few minutes and try again.", headers={"Retry-After": "900"})


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class SignupBody(Credentials):
    inviteCode: str | None = Field(default=None, max_length=200)


class PasswordBody(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


class PasswordOnly(BaseModel):
    password: str = Field(max_length=200)


class EmailOnly(BaseModel):
    email: str = Field(max_length=254)


class ResetBody(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=200)


# ---------------------------------------------------------------------------------------------- public
@router.get("/api/auth/config")
async def auth_config():
    return {"authRequired": config.AUTH_REQUIRED, "signupOpen": config.ALLOW_SIGNUP, "inviteRequired": bool(config.INVITE_CODE),
            "passwordResetByEmail": mail.configured(), "minPasswordLength": config.MIN_PASSWORD_LENGTH,
            "siteName": config.SITE_NAME, "contactEmail": config.CONTACT_EMAIL}


@router.post("/api/auth/signup")
async def signup(body: SignupBody, request: Request, response: Response):
    if not config.AUTH_REQUIRED:
        raise HTTPException(404, "Accounts are switched off on this server.")
    if not config.ALLOW_SIGNUP:
        raise HTTPException(403, "Sign-ups are closed.")
    ip = client_ip(request)
    if not auth.limiter.hit(f"signup:{ip}", 10, 3600):
        raise _too_many()
    if config.INVITE_CODE and not hmac.compare_digest((body.inviteCode or "").strip().encode(), config.INVITE_CODE.encode()):
        raise HTTPException(403, "That invite code is not valid.")
    try:
        user = await asyncio.to_thread(auth.create_user, body.email, body.password)
    except AuthError as e:
        raise HTTPException(e.status, str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this e-mail already exists.")
    set_session_cookie(response, auth.start_session(user.id, ip, request.headers.get("user-agent", "")))
    with db.as_user(user.id):
        return user_json(user)


@router.post("/api/auth/login")
async def login(body: Credentials, request: Request, response: Response):
    if not config.AUTH_REQUIRED:
        raise HTTPException(404, "Accounts are switched off on this server.")
    ip = client_ip(request)
    email_key = f"login-email:{body.email.strip().lower()[:254]}"
    # Failed attempts count per address and per e-mail, so neither one machine nor one targeted account can be hammered.
    if auth.limiter.blocked(f"login-ip:{ip}", config.AUTH_ATTEMPTS_PER_15_MIN * 3, 900) or \
            auth.limiter.blocked(email_key, config.AUTH_ATTEMPTS_PER_15_MIN, 900):
        raise _too_many()
    user = await asyncio.to_thread(auth.authenticate, body.email, body.password)
    if user is None:
        auth.limiter.hit(f"login-ip:{ip}", 10_000, 900)
        auth.limiter.hit(email_key, 10_000, 900)
        raise HTTPException(401, "That e-mail and password do not match, or the account is disabled.")
    set_session_cookie(response, auth.start_session(user.id, ip, request.headers.get("user-agent", "")))
    with db.as_user(user.id):
        return user_json(user)


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    auth.end_session(request.scope.get("state", {}).get("session_token"))
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/api/auth/me")
async def me():
    user = auth.current_user()
    if user is None and not config.AUTH_REQUIRED:
        user = auth.LOCAL_USER
    if user is None:
        raise HTTPException(401, "Not signed in.", headers={"Cache-Control": "no-store"})
    return user_json(user)


@router.post("/api/auth/forgot")
async def forgot(body: EmailOnly, request: Request):
    """Always answers the same, so the form cannot be used to find out who has an account."""
    answer = {"ok": True, "message": "If that address has an account, a reset link is on its way."}
    ip = client_ip(request)
    if not config.AUTH_REQUIRED or not auth.limiter.hit(f"forgot:{ip}", 5, 3600) or not mail.configured():
        return answer
    try:
        email = auth.normalize_email(body.email)
    except AuthError:
        return answer
    row = db.one("SELECT id, disabled FROM users WHERE email=?", (email,))
    if row and not row["disabled"] and auth.limiter.hit(f"forgot-email:{email}", 3, 3600):
        token = auth.create_reset_token(int(row["id"]))
        link = f"{config.PUBLIC_URL or ''}/reset?token={token}"
        await mail.send(email, f"Reset your {config.SITE_NAME} password",
                        f"Someone asked to reset the password for this address.\n\nOpen this link within {auth.RESET_MINUTES} minutes to choose a new one:\n{link}\n\n"
                        "If this was not you, ignore this message. Your password has not changed.")
    return answer


@router.post("/api/auth/reset")
async def reset(body: ResetBody, request: Request, response: Response):
    ip = client_ip(request)
    if not auth.limiter.hit(f"reset:{ip}", 10, 900):
        raise _too_many()
    try:
        auth.check_new_password(body.password)   # before the token is used up, so a weak password does not burn the link
    except AuthError as e:
        raise HTTPException(e.status, str(e))
    user_id = auth.consume_reset_token(body.token)
    if user_id is None:
        raise HTTPException(400, "This reset link is invalid or has expired. Request a new one.")
    try:
        await asyncio.to_thread(auth.set_password, user_id, body.password)
    except AuthError as e:
        raise HTTPException(e.status, str(e))
    row = db.one("SELECT * FROM users WHERE id=?", (user_id,))
    if row is None or row["disabled"]:
        raise HTTPException(400, "This reset link is invalid or has expired. Request a new one.")
    set_session_cookie(response, auth.start_session(user_id, ip, request.headers.get("user-agent", "")))
    return {"ok": True}


# ---------------------------------------------------------------------------------------------- signed-in account
@router.post("/api/auth/password")
async def change_password(body: PasswordBody, request: Request):
    user = require_user()
    if user.id == 0:
        raise HTTPException(404, "Accounts are switched off on this server.")
    row = db.one("SELECT pw_hash FROM users WHERE id=?", (user.id,))
    if not row or not await asyncio.to_thread(auth.verify_password, body.current, row["pw_hash"]):
        raise HTTPException(403, "The current password is not correct.")
    try:
        await asyncio.to_thread(auth.set_password, user.id, body.new, keep_session=request.scope.get("state", {}).get("session_token"))
    except AuthError as e:
        raise HTTPException(e.status, str(e))
    return {"ok": True}


def purge_user_data(user_id: int) -> dict:
    """Delete everything an account owns. The spending log keeps its numbers (it holds no content)."""
    with db.as_user(user_id):
        chat_ids = [r["id"] for r in db.q("SELECT id FROM chats WHERE user_id=?", (user_id,))]
        for cid in chat_ids:
            memory.delete_chat(cid, True)
        with db.tx() as c:
            c.execute("DELETE FROM fact_fts WHERE fact_id IN (SELECT id FROM facts WHERE user_id=?)", (user_id,))
            c.execute("DELETE FROM facts WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM settings WHERE key LIKE ?", (f"u{user_id}:%",))
            c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM password_resets WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM users WHERE id=?", (user_id,))
    return {"chats": len(chat_ids)}


@router.delete("/api/auth/account")
async def delete_account(body: PasswordOnly, response: Response):
    user = require_user()
    if user.id == 0:
        raise HTTPException(404, "Accounts are switched off on this server.")
    row = db.one("SELECT pw_hash FROM users WHERE id=?", (user.id,))
    if not row or not await asyncio.to_thread(auth.verify_password, body.password, row["pw_hash"]):
        raise HTTPException(403, "The password is not correct.")
    result = await asyncio.to_thread(purge_user_data, user.id)
    clear_session_cookie(response)
    return {"deleted": True, **result}


# ---------------------------------------------------------------------------------------------- admin
class UserPatch(BaseModel):
    disabled: bool | None = None
    isAdmin: bool | None = None
    monthlyCap: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    resetCap: bool = False   # back to the server default


@router.get("/api/admin/users")
async def admin_users():
    require_admin()
    rows = db.q(
        "SELECT u.id, u.email, u.created, u.last_login, u.is_admin, u.disabled, u.monthly_cap, "
        "COALESCE((SELECT SUM(cost) FROM calls c WHERE c.user_id=u.id AND c.ts>=?),0) spent, "
        "(SELECT COUNT(*) FROM chats WHERE user_id=u.id) chats FROM users u ORDER BY u.created DESC LIMIT 500", (usage.month_start(),))
    return [{"id": r["id"], "email": r["email"], "created": r["created"], "lastLogin": r["last_login"], "isAdmin": bool(r["is_admin"]),
             "disabled": bool(r["disabled"]), "monthlyCap": r["monthly_cap"], "effectiveCap": r["monthly_cap"] if r["monthly_cap"] is not None else config.DEFAULT_USER_MONTHLY_USD,
             "monthSpentUsd": round(float(r["spent"]), 6), "chats": r["chats"]} for r in rows]


@router.patch("/api/admin/users/{user_id}")
async def admin_patch_user(user_id: int, body: UserPatch):
    me_ = require_admin()
    if not db.one("SELECT 1 FROM users WHERE id=?", (user_id,)):
        raise HTTPException(404, "Unknown user")
    if user_id == me_.id and (body.disabled or body.isAdmin is False):
        raise HTTPException(409, "You cannot disable or demote your own account.")
    if body.disabled is not None:
        db.run("UPDATE users SET disabled=? WHERE id=?", (int(body.disabled), user_id))
        if body.disabled:
            auth.end_sessions(user_id)
    if body.isAdmin is not None:
        db.run("UPDATE users SET is_admin=? WHERE id=?", (int(body.isAdmin), user_id))
    if body.resetCap:
        db.run("UPDATE users SET monthly_cap=NULL WHERE id=?", (user_id,))
    elif body.monthlyCap is not None:
        db.run("UPDATE users SET monthly_cap=? WHERE id=?", (body.monthlyCap, user_id))
    return {"ok": True}


@router.get("/api/admin/stats")
async def admin_stats():
    require_admin()
    from app.pipeline.engine import manager
    return {"users": db.one("SELECT COUNT(*) n FROM users")["n"], "chats": db.one("SELECT COUNT(*) n FROM chats")["n"],
            "monthSpentUsd": round(usage.global_month_spent(), 6), "globalCapUsd": config.GLOBAL_MONTHLY_USD,
            "activeRuns": sum(1 for r in manager.runs.values() if not r.finished), "maxConcurrentRuns": config.MAX_CONCURRENT_RUNS}
