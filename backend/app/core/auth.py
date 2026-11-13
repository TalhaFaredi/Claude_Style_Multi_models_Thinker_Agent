"""Accounts: password hashing, login sessions, rate limiting and the signed-in user of the current request.

Design notes
  * Passwords: scrypt from the standard library (memory-hard, no extra dependency). The parameters are stored with
    every hash, so they can be raised later without locking anyone out.
  * Sessions: a random 256-bit token in an HttpOnly cookie. Only its SHA-256 is stored, so a leaked database cannot
    be replayed as logins. Sessions expire, slide forward while in use and end on logout or a password change.
  * The current user travels in a ContextVar (see core/db.py for the user id every query filters by).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass

from app.core import config, db

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1     # about 32 MB and 0.1 s per hash
SCRYPT_MAXMEM = 128 * 1024 * 1024
MAX_PASSWORD_LENGTH = 128                        # bounds the work an attacker can force per request
SESSION_COOKIE = "session"
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,}$")


@dataclass(frozen=True)
class User:
    id: int
    email: str
    is_admin: bool = False


LOCAL_USER = User(0, "local", True)   # single-user mode (AUTH_REQUIRED=0)
_current: ContextVar[User | None] = ContextVar("current_user", default=None)


def current_user() -> User | None:
    return _current.get()


def set_current(user: User | None):
    return _current.set(user)


def reset_current(token) -> None:
    _current.reset(token)


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------------------------- passwords
def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=SCRYPT_MAXMEM, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return "scrypt${}${}${}${}${}".format(SCRYPT_N, SCRYPT_R, SCRYPT_P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _scrypt(password[:MAX_PASSWORD_LENGTH + 1], base64.b64decode(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password("not-a-real-password")


def burn_password_time(password: str) -> None:
    """Take as long as a real check, so an unknown e-mail cannot be told apart from a wrong password by timing."""
    verify_password(password, _DUMMY_HASH)


def check_new_password(password: str, email: str = "") -> None:
    if len(password) < config.MIN_PASSWORD_LENGTH:
        raise AuthError(f"Use a password of at least {config.MIN_PASSWORD_LENGTH} characters.", 422)
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"Use a password of at most {MAX_PASSWORD_LENGTH} characters.", 422)
    if password.lower() == email.lower() or password.lower() in _COMMON:
        raise AuthError("That password is too easy to guess. Choose another.", 422)


_COMMON = {"password12", "password123", "1234567890", "qwertyuiop", "iloveyou12", "password1234", "letmein1234", "administrator", "0123456789",
           "11111111111", "passw0rd123", "welcome1234"}


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise AuthError("Enter a valid e-mail address.", 422)
    return email


# ---------------------------------------------------------------------------------------------- users
def _user_from_row(row) -> User:
    return User(int(row["id"]), row["email"], bool(row["is_admin"]))


def create_user(email: str, password: str, *, is_admin: bool = False) -> User:
    email = normalize_email(email)
    check_new_password(password, email)
    if db.one("SELECT 1 FROM users WHERE email=?", (email,)):
        raise AuthError("An account with this e-mail already exists.", 409)
    is_admin = is_admin or email in config.ADMIN_EMAILS
    uid = db.run("INSERT INTO users(email,pw_hash,created,is_admin) VALUES(?,?,?,?)", (email, hash_password(password), db.now(), int(is_admin)))
    return User(uid, email, is_admin)


def authenticate(email: str, password: str) -> User | None:
    """The user if the e-mail and password match and the account is enabled; otherwise None (same work either way)."""
    try:
        email = normalize_email(email)
    except AuthError:
        burn_password_time(password)
        return None
    row = db.one("SELECT * FROM users WHERE email=?", (email,))
    if not row:
        burn_password_time(password)
        return None
    ok = verify_password(password, row["pw_hash"])
    if not ok or row["disabled"]:
        return None
    db.run("UPDATE users SET last_login=? WHERE id=?", (db.now(), row["id"]))
    return _user_from_row(row)


def set_password(user_id: int, password: str, *, keep_session: str | None = None) -> None:
    row = db.one("SELECT email FROM users WHERE id=?", (user_id,))
    check_new_password(password, row["email"] if row else "")
    db.run("UPDATE users SET pw_hash=? WHERE id=?", (hash_password(password), user_id))
    end_sessions(user_id, except_token=keep_session)   # a changed password signs every other device out
    db.run("DELETE FROM password_resets WHERE user_id=?", (user_id,))


# ---------------------------------------------------------------------------------------------- sessions
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(user_id: int, ip: str = "", agent: str = "") -> str:
    token = secrets.token_urlsafe(32)
    now = db.now()
    db.run("INSERT INTO sessions(token_hash,user_id,created,last_seen,expires,ip,agent) VALUES(?,?,?,?,?,?,?)",
           (_hash(token), user_id, now, now, now + config.SESSION_DAYS * 86400, ip[:64], agent[:200]))
    db.run("DELETE FROM sessions WHERE expires<?", (now,))   # housekeeping: expired sessions are removed as new ones start
    return token


def session_user(token: str | None) -> User | None:
    if not token or len(token) > 200:
        return None
    row = db.one("SELECT s.token_hash, s.last_seen, s.expires, u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (_hash(token),))
    now = db.now()
    if not row or row["expires"] < now or row["disabled"]:
        return None
    if now - row["last_seen"] > 3600:   # sliding expiry, written at most once an hour
        db.run("UPDATE sessions SET last_seen=?, expires=? WHERE token_hash=?", (now, now + config.SESSION_DAYS * 86400, row["token_hash"]))
    return _user_from_row(row)


def end_session(token: str | None) -> None:
    if token:
        db.run("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))


def end_sessions(user_id: int, except_token: str | None = None) -> None:
    if except_token:
        db.run("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user_id, _hash(except_token)))
    else:
        db.run("DELETE FROM sessions WHERE user_id=?", (user_id,))


# ---------------------------------------------------------------------------------------------- password reset
RESET_MINUTES = 60


def create_reset_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.run("DELETE FROM password_resets WHERE user_id=? OR expires<?", (user_id, db.now()))
    db.run("INSERT INTO password_resets(token_hash,user_id,expires) VALUES(?,?,?)", (_hash(token), user_id, db.now() + RESET_MINUTES * 60))
    return token


def consume_reset_token(token: str) -> int | None:
    """The user id the token belongs to; the token is single-use."""
    row = db.one("SELECT * FROM password_resets WHERE token_hash=?", (_hash(token or ""),))
    if not row:
        return None
    db.run("DELETE FROM password_resets WHERE token_hash=?", (row["token_hash"],))
    return int(row["user_id"]) if row["expires"] >= db.now() else None


# ---------------------------------------------------------------------------------------------- rate limiting
class Limiter:
    """Sliding-window counter kept in memory (one server process). `hit` counts and tells whether the call may go on;
    `blocked` only asks. Old keys are dropped so the table cannot grow without bound."""

    def __init__(self) -> None:
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self._swept = time.monotonic()

    def _trim(self, key: str, window: float) -> deque[float]:
        q = self.events[key]
        cutoff = time.monotonic() - window
        while q and q[0] < cutoff:
            q.popleft()
        if time.monotonic() - self._swept > 600:
            self._swept = time.monotonic()
            for k in [k for k, v in self.events.items() if not v or v[-1] < cutoff - 3600]:
                self.events.pop(k, None)
        return q

    def blocked(self, key: str, limit: int, window: float) -> bool:
        return len(self._trim(key, window)) >= limit

    def hit(self, key: str, limit: int, window: float) -> bool:
        q = self._trim(key, window)
        if len(q) >= limit:
            return False
        q.append(time.monotonic())
        return True

    def clear(self) -> None:
        self.events.clear()


limiter = Limiter()
