"""Accounts and multi-user isolation. These switch AUTH_REQUIRED on (the rest of the suite runs in single-user mode)."""
from __future__ import annotations

import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.core import auth, config, db, usage
from app.main import app

PASSWORD = "correct horse battery"
ORIGIN = {"Origin": "http://localhost:3000"}


@pytest.fixture(autouse=True)
def accounts_on(monkeypatch):
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    monkeypatch.setattr(config, "ALLOW_SIGNUP", True)
    monkeypatch.setattr(config, "INVITE_CODE", "")
    monkeypatch.setattr(config, "ADMIN_EMAILS", {"boss@example.com"})
    auth.limiter.clear()


def new_client(email: str | None = None, password: str = PASSWORD) -> TestClient:
    c = TestClient(app, headers=ORIGIN)
    if email:
        r = c.post("/api/auth/signup", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
    return c


def uid_of(email: str) -> int:
    return db.one("SELECT id FROM users WHERE email=?", (email,))["id"]


def make_chat(c: TestClient, email: str, text: str = "hello") -> str:
    chat = c.post("/api/chats", json={"title": "mine"}).json()
    from app import memory
    with db.as_user(uid_of(email)):
        memory.add_message(chat["id"], "user", text)
        memory.add_message(chat["id"], "assistant", "an answer")
    return chat["id"]


# ------------------------------------------------------------------------------------------------ sign-up and sessions
def test_api_needs_a_session_but_health_and_config_are_public():
    c = new_client()
    assert c.get("/health").status_code == 200
    assert c.get("/api/auth/config").json()["signupOpen"] is True
    for path in ("/api/chats", "/api/config", "/api/models", "/api/memory", "/api/usage", "/api/settings"):
        r = c.get(path)
        assert r.status_code == 401 and r.json()["code"] == "auth_required", path
    assert c.get("/api/auth/me").status_code == 401


def test_signup_sets_a_hardened_cookie_and_me_works():
    c = new_client()
    r = c.post("/api/auth/signup", json={"email": "Ann@Example.com", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["email"] == "ann@example.com" and r.json()["isAdmin"] is False
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert c.get("/api/auth/me").json()["email"] == "ann@example.com"
    assert c.get("/api/chats").status_code == 200


def test_session_token_is_stored_only_as_a_hash():
    c = new_client("hash@example.com")
    token = c.cookies.get("session")
    assert token and not db.one("SELECT 1 FROM sessions WHERE token_hash=?", (token,))
    assert db.one("SELECT 1 FROM sessions WHERE token_hash=?", (auth._hash(token),))
    assert "scrypt$" in db.one("SELECT pw_hash FROM users WHERE email='hash@example.com'")["pw_hash"]


def test_secure_flag_follows_config(monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    r = TestClient(app, headers=ORIGIN).post("/api/auth/signup", json={"email": "s@example.com", "password": PASSWORD})
    assert "secure" in r.headers["set-cookie"].lower()


@pytest.mark.parametrize("email,password,status", [
    ("not-an-email", PASSWORD, 422), ("a@b", PASSWORD, 422), ("x@example.com", "short", 422),
    ("x@example.com", "password123", 422), ("x@example.com", "x" * 129, 422),
])
def test_signup_validation(email, password, status):
    assert new_client().post("/api/auth/signup", json={"email": email, "password": password}).status_code == status


def test_duplicate_email_is_refused_case_insensitively():
    new_client("dup@example.com")
    assert new_client().post("/api/auth/signup", json={"email": "DUP@example.com", "password": PASSWORD}).status_code == 409


def test_signup_can_be_closed_or_need_an_invite(monkeypatch):
    monkeypatch.setattr(config, "ALLOW_SIGNUP", False)
    assert new_client().post("/api/auth/signup", json={"email": "c@example.com", "password": PASSWORD}).status_code == 403
    monkeypatch.setattr(config, "ALLOW_SIGNUP", True)
    monkeypatch.setattr(config, "INVITE_CODE", "open-sesame")
    c = new_client()
    assert c.post("/api/auth/signup", json={"email": "c@example.com", "password": PASSWORD}).status_code == 403
    assert c.post("/api/auth/signup", json={"email": "c@example.com", "password": PASSWORD, "inviteCode": "wrong"}).status_code == 403
    assert c.post("/api/auth/signup", json={"email": "c@example.com", "password": PASSWORD, "inviteCode": "open-sesame"}).status_code == 200


def test_login_logout_and_wrong_password():
    new_client("login@example.com")
    c = new_client()
    assert c.post("/api/auth/login", json={"email": "login@example.com", "password": "wrong password!"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "LOGIN@example.com", "password": PASSWORD}).status_code == 200
    assert c.get("/api/chats").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/chats").status_code == 401   # the server forgot the session, not only the browser


def test_repeated_failures_lock_the_login_for_a_while():
    new_client("lock@example.com")
    c = new_client()
    codes = [c.post("/api/auth/login", json={"email": "lock@example.com", "password": f"wrong password {i}"}).status_code
             for i in range(config.AUTH_ATTEMPTS_PER_15_MIN + 2)]
    assert codes[0] == 401 and codes[-1] == 429
    # even the right password is refused while locked, so guessing cannot continue
    assert c.post("/api/auth/login", json={"email": "lock@example.com", "password": PASSWORD}).status_code == 429


def test_disabled_account_and_expired_session_cannot_sign_in():
    c = new_client("off@example.com")
    db.run("UPDATE users SET disabled=1 WHERE email='off@example.com'")
    assert c.get("/api/chats").status_code == 401
    assert new_client().post("/api/auth/login", json={"email": "off@example.com", "password": PASSWORD}).status_code == 401
    db.run("UPDATE users SET disabled=0 WHERE email='off@example.com'")
    assert c.get("/api/chats").status_code == 200
    db.run("UPDATE sessions SET expires=?", (time.time() - 1,))
    assert c.get("/api/chats").status_code == 401


# ------------------------------------------------------------------------------------------------ CSRF
def test_cross_site_state_changing_requests_are_refused():
    c = new_client("csrf@example.com")
    evil = {"Origin": "https://evil.example"}
    assert c.post("/api/chats", json={"title": "x"}, headers=evil).status_code == 403
    assert c.put("/api/settings", json={"longMemory": False}, headers=evil).status_code == 403
    assert c.post("/api/chats", json={"title": "x"}, headers=ORIGIN).status_code == 200
    assert c.get("/api/chats", headers=evil).status_code == 200   # reads are not state-changing and CORS stops the page reading them


def test_public_url_is_an_allowed_origin(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "https://assistant.example.com")
    c = new_client("pu@example.com")
    assert c.post("/api/chats", json={"title": "x"}, headers={"Origin": "https://assistant.example.com"}).status_code == 200


# ------------------------------------------------------------------------------------------------ isolation
def test_users_cannot_see_or_touch_each_others_chats():
    a, b = new_client("a@example.com"), new_client("b@example.com")
    chat = make_chat(a, "a@example.com", "secret plan for launch")
    assert [x["id"] for x in a.get("/api/chats").json()] == [chat]
    assert b.get("/api/chats").json() == []
    assert b.get("/api/chats", params={"q": "secret"}).json() == []
    for method, path, body in [
        ("get", f"/api/chats/{chat}", None), ("patch", f"/api/chats/{chat}", {"title": "pwned"}), ("delete", f"/api/chats/{chat}", None),
        ("get", f"/api/chats/{chat}/ledger", None), ("get", f"/api/chats/{chat}/export", None),
        ("post", f"/api/chats/{chat}/fork", {"model": "x"}), ("post", f"/api/chats/{chat}/compact", {"model": "x"}),
    ]:
        r = getattr(b, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (method, path, r.status_code)
    # the owner's chat is untouched
    assert a.get(f"/api/chats/{chat}").json()["chat"]["title"] == "mine"


def test_a_foreign_chat_id_cannot_be_adopted_or_written_to():
    a, b = new_client("a@example.com"), new_client("b@example.com")
    chat = make_chat(a, "a@example.com")
    assert b.get(f"/api/chats/{chat}/context", params={"model": "x"}).status_code == 404     # ensure_chat must not create or reuse it
    assert b.post(f"/api/chats/{chat}/files", files={"file": ("n.txt", b"hello world", "text/plain")}).status_code == 404
    run = {"id": "r-foreign", "chatId": chat, "prompt": "hi", "simple": {"model": "m"}, "team": {"model": "m"}}
    assert b.post("/api/runs", json=run).status_code == 404
    assert db.one("SELECT user_id FROM chats WHERE id=?", (chat,))["user_id"] == uid_of("a@example.com")
    assert db.one("SELECT COUNT(*) n FROM messages WHERE chat_id=?", (chat,))["n"] == 2


def test_files_are_only_reachable_through_your_own_chat():
    a, b = new_client("a@example.com"), new_client("b@example.com")
    chat_a = a.post("/api/chats", json={}).json()["id"]
    up = a.post(f"/api/chats/{chat_a}/files", files={"file": ("notes.txt", b"only for a", "text/plain")})
    assert up.status_code == 200
    fp = up.json()["fingerprint"]
    chat_b = b.post("/api/chats", json={}).json()["id"]
    assert b.get(f"/api/files/{fp}", params={"chatId": chat_a}).status_code == 404    # not via a's chat id
    assert b.get(f"/api/files/{fp}", params={"chatId": chat_b}).status_code == 404    # not via his own chat either
    assert b.post(f"/api/files/{fp}/read", json={"chatId": chat_a, "textOnly": True}).status_code == 404
    assert b.delete(f"/api/chats/{chat_a}/files/{fp}").status_code == 404
    assert a.get(f"/api/files/{fp}", params={"chatId": chat_a}).status_code == 200


def test_long_term_memory_is_private():
    from app import memory
    a, b = new_client("a@example.com"), new_client("b@example.com")
    with db.as_user(uid_of("a@example.com")):
        fid = memory.add_fact("My bank is Acme", "chat", None)
        hits = memory.relevant_facts("bank")
    assert [h["id"] for h in hits] == [fid]
    assert b.get("/api/memory").json()["facts"] == []
    with db.as_user(uid_of("b@example.com")):
        assert memory.relevant_facts("bank") == []
    assert b.delete(f"/api/memory/{fid}").status_code == 404
    assert len(a.get("/api/memory").json()["facts"]) == 1
    assert a.delete(f"/api/memory/{fid}").status_code == 200


def test_settings_and_usage_are_per_user():
    a, b = new_client("a@example.com"), new_client("b@example.com")
    assert a.put("/api/settings", json={"longMemory": False}).json()["longMemory"] is False
    assert b.get("/api/settings").json()["longMemory"] is True
    db.run("INSERT INTO calls(ts,model,cost,ok,user_id) VALUES(?,?,?,?,?)", (time.time(), "m", 0.5, 1, uid_of("a@example.com")))
    assert a.get("/api/usage").json()["totalUsd"] == 0.5
    assert b.get("/api/usage").json()["totalUsd"] == 0.0
    assert b.get("/api/config").json()["monthUsd"] == 0.0


def test_ratings_and_generated_files_are_private(tmp_path):
    a, b = new_client("a@example.com"), new_client("b@example.com")
    chat = make_chat(a, "a@example.com")
    mid = db.one("SELECT id FROM messages WHERE chat_id=? AND role='assistant'", (chat,))["id"]
    b.post(f"/api/messages/{mid}/rating", json={"value": 1})
    assert db.one("SELECT rating FROM messages WHERE id=?", (mid,))["rating"] is None
    a.post(f"/api/messages/{mid}/rating", json={"value": 1})
    assert db.one("SELECT rating FROM messages WHERE id=?", (mid,))["rating"] == 1
    path = tmp_path / "report.txt"
    path.write_text("private report")
    aid = "a" * 16
    db.run("INSERT INTO artifacts(id,chat_id,name,path,mime,ts,user_id) VALUES(?,?,?,?,?,?,?)", (aid, chat, "report.txt", str(path), "text/plain", time.time(), uid_of("a@example.com")))
    assert a.get(f"/api/artifacts/{aid}").status_code == 200
    assert b.get(f"/api/artifacts/{aid}").status_code == 404
    assert new_client().get(f"/api/artifacts/{aid}").status_code == 401


def test_runs_cannot_be_controlled_by_other_users():
    from app.pipeline.engine import Run, manager
    from app.pipeline.runtime import RunContext
    a, b = new_client("a@example.com"), new_client("b@example.com")
    chat = make_chat(a, "a@example.com")

    class Rc:
        chat_id = chat
        awaiting_approval = True
        approval_version = "v1"
        view: dict = {}
        permissions: dict = {}

    manager.runs["run-a"] = Run(Rc(), owner=uid_of("a@example.com"))   # type: ignore[arg-type]
    for path in ("approve", "stop", "permission"):
        r = b.post(f"/api/runs/run-a/{path}", json={"id": "p", "allow": True} if path == "permission" else None)
        assert r.status_code == 404, path
    assert manager.runs["run-a"].finished is False


def test_export_and_import_move_a_chat_between_accounts_without_leaking():
    a, b = new_client("a@example.com"), new_client("b@example.com")
    chat = make_chat(a, "a@example.com", "remember the number 42")
    zipped = a.get(f"/api/chats/{chat}/export")
    assert zipped.status_code == 200
    r = b.post("/api/import", files={"file": ("chat.zip", io.BytesIO(zipped.content), "application/zip")})
    assert r.status_code == 200, r.text
    imported = r.json()["chatId"]
    assert [c["id"] for c in b.get("/api/chats").json()] == [imported]
    assert [c["id"] for c in a.get("/api/chats").json()] == [chat]
    assert b.get(f"/api/chats/{imported}").json()["messages"][0]["text"] == "remember the number 42"


def test_import_does_not_trust_readings_or_fingerprints_from_an_archive():
    """A crafted archive must not plant fake readings in the cache that is shared between users."""
    import zipfile
    from app.files.common import fingerprint
    a, b = new_client("a@example.com"), new_client("b@example.com")
    victim_bytes = b"the real document everyone has"
    fp = fingerprint(victim_bytes)
    chat = make_chat(a, "a@example.com")
    good = a.get(f"/api/chats/{chat}/export").content
    src = zipfile.ZipFile(io.BytesIO(good))
    parts = {n: src.read(n) for n in src.namelist()}
    manifest = json.loads(parts["manifest.json"])
    reading = json.dumps({"fingerprint": fp, "name": "doc.txt", "size": 5, "reader": "text", "version": config.PARSE_VERSION,
                          "pages": [{"page": 1, "text": "FAKE TEXT PLANTED BY ATTACKER", "kind": "text"}], "card": {}, "cost": 0, "analysis": {"pages": []}}).encode()
    parts[f"readings/{fp}.text.json"] = reading
    parts["files.json"] = json.dumps([{"fingerprint": fp, "name": "doc.txt", "size": 5, "pages": 1, "kinds": '{"pages":[]}', "reader": "text"}]).encode()
    import hashlib
    manifest["checksums"] = {n: hashlib.sha256(v).hexdigest() for n, v in parts.items() if n != "manifest.json"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        for n, v in parts.items():
            if n != "manifest.json":
                z.writestr(n, v)
    assert a.post("/api/import", files={"file": ("evil.zip", buf.getvalue(), "application/zip")}).status_code == 200
    assert db.one("SELECT 1 FROM files WHERE fingerprint=?", (fp,)) is None
    assert db.one("SELECT 1 FROM readings WHERE fingerprint=?", (fp,)) is None


# ------------------------------------------------------------------------------------------------ money
def test_monthly_allowance_blocks_new_questions_with_402(monkeypatch):
    c = new_client("spender@example.com")
    chat = c.post("/api/chats", json={}).json()["id"]
    run = {"id": "r1", "chatId": chat, "prompt": "hi", "simple": {"model": "m"}, "team": {"model": "m"}}
    cap = config.DEFAULT_USER_MONTHLY_USD
    with db.as_user(uid_of("spender@example.com")):
        assert usage.month_cap() == cap
    db.run("INSERT INTO calls(ts,model,cost,ok,user_id) VALUES(?,?,?,?,?)", (time.time(), "m", cap, 1, uid_of("spender@example.com")))
    r = c.post("/api/runs", json=run)
    assert r.status_code == 402 and r.json()["code"] == "allowance_used"
    assert c.post(f"/api/chats/{chat}/compact", json={"model": "m"}).status_code == 402
    # another user is unaffected
    assert new_client("other@example.com").get("/api/config").json()["monthUsd"] == 0.0


def test_global_cap_stops_everyone(monkeypatch):
    monkeypatch.setattr(config, "GLOBAL_MONTHLY_USD", 1.0)
    c = new_client("g@example.com")
    chat = c.post("/api/chats", json={}).json()["id"]
    db.run("INSERT INTO calls(ts,model,cost,ok,user_id) VALUES(?,?,?,?,?)", (time.time(), "m", 1.0, 1, 999))
    r = c.post("/api/runs", json={"id": "r2", "chatId": chat, "prompt": "hi", "simple": {"model": "m"}, "team": {"model": "m"}})
    assert r.status_code == 402


def test_question_budget_is_clamped_by_the_server():
    new_client("clamp@example.com")
    uid = uid_of("clamp@example.com")
    with db.as_user(uid):
        assert usage.limit_budget(50.0) == config.MAX_RUN_USD
        db.run("INSERT INTO calls(ts,model,cost,ok,user_id) VALUES(?,?,?,?,?)", (time.time(), "m", config.DEFAULT_USER_MONTHLY_USD - 0.1, 1, uid))
        assert usage.limit_budget(50.0) == pytest.approx(0.1)


def test_user_cannot_raise_their_own_caps_in_settings():
    c = new_client("caps@example.com")
    s = c.put("/api/settings", json={"monthBudget": 1000, "askLimit": 50}).json()
    assert s["monthBudget"] == config.DEFAULT_USER_MONTHLY_USD and s["askLimit"] == config.MAX_RUN_USD
    db.run("UPDATE users SET monthly_cap=10 WHERE email='caps@example.com'")
    assert c.put("/api/settings", json={"monthBudget": 1000}).json()["monthBudget"] == 10


def test_busy_server_refuses_politely(monkeypatch):
    from app.pipeline.engine import manager
    c = new_client("busy@example.com")
    chat = c.post("/api/chats", json={}).json()["id"]
    monkeypatch.setattr(manager, "load", lambda owner: (config.MAX_CONCURRENT_RUNS, 0))
    r = c.post("/api/runs", json={"id": "r3", "chatId": chat, "prompt": "hi", "simple": {"model": "m"}, "team": {"model": "m"}})
    assert r.status_code == 503
    monkeypatch.setattr(manager, "load", lambda owner: (1, config.MAX_RUNS_PER_USER))
    assert c.post("/api/runs", json={"id": "r4", "chatId": chat, "prompt": "hi", "simple": {"model": "m"}, "team": {"model": "m"}}).status_code == 429


def test_storage_quota(monkeypatch):
    monkeypatch.setattr(config, "MAX_USER_STORAGE_MB", 0)
    c = new_client("quota@example.com")
    chat = c.post("/api/chats", json={}).json()["id"]
    assert c.post(f"/api/chats/{chat}/files", files={"file": ("n.txt", b"hello world", "text/plain")}).status_code == 413


# ------------------------------------------------------------------------------------------------ account management and admin
def test_change_password_signs_out_other_devices():
    phone, laptop = new_client("pw@example.com"), new_client()
    assert laptop.post("/api/auth/login", json={"email": "pw@example.com", "password": PASSWORD}).status_code == 200
    assert phone.post("/api/auth/password", json={"current": "wrong wrong wrong", "new": "another long phrase"}).status_code == 403
    assert phone.post("/api/auth/password", json={"current": PASSWORD, "new": "short"}).status_code == 422
    assert phone.post("/api/auth/password", json={"current": PASSWORD, "new": "another long phrase"}).status_code == 200
    assert phone.get("/api/chats").status_code == 200
    assert laptop.get("/api/chats").status_code == 401
    assert new_client().post("/api/auth/login", json={"email": "pw@example.com", "password": PASSWORD}).status_code == 401
    assert new_client().post("/api/auth/login", json={"email": "pw@example.com", "password": "another long phrase"}).status_code == 200


def test_delete_account_removes_everything_it_owned():
    from app import memory
    a, b = new_client("gone@example.com"), new_client("stay@example.com")
    chat = make_chat(a, "gone@example.com", "private words")
    with db.as_user(uid_of("gone@example.com")):
        memory.add_fact("I live somewhere", "chat", chat)
    keep = make_chat(b, "stay@example.com")
    uid = uid_of("gone@example.com")
    assert a.request("DELETE", "/api/auth/account", json={"password": "wrong wrong wrong"}).status_code == 403
    assert a.request("DELETE", "/api/auth/account", json={"password": PASSWORD}).status_code == 200
    for table in ("chats", "facts", "sessions"):
        assert db.one(f"SELECT COUNT(*) n FROM {table} WHERE user_id=?", (uid,))["n"] == 0
    assert db.one("SELECT COUNT(*) n FROM messages WHERE chat_id=?", (chat,))["n"] == 0
    assert db.one("SELECT 1 FROM users WHERE id=?", (uid,)) is None
    assert a.get("/api/chats").status_code == 401
    assert [c["id"] for c in b.get("/api/chats").json()] == [keep]


def test_password_reset_flow(monkeypatch):
    sent = []

    async def fake_send(to, subject, body):
        sent.append((to, body))
        return True

    from app.core import mail
    monkeypatch.setattr(mail, "send", fake_send)
    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(config, "PUBLIC_URL", "https://assistant.example.com")
    old = new_client("reset@example.com")
    c = new_client()
    # same answer for a known and an unknown address
    r1 = c.post("/api/auth/forgot", json={"email": "reset@example.com"})
    r2 = c.post("/api/auth/forgot", json={"email": "nobody@example.com"})
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    assert len(sent) == 1 and sent[0][0] == "reset@example.com"
    token = sent[0][1].split("token=")[1].split()[0]
    assert c.post("/api/auth/reset", json={"token": "bogus", "password": "a brand new phrase"}).status_code == 400
    assert c.post("/api/auth/reset", json={"token": token, "password": "short"}).status_code == 422   # a weak password does not burn the link
    r = new_client().post("/api/auth/reset", json={"token": token, "password": "a brand new phrase"})
    assert r.status_code == 200
    assert old.get("/api/chats").status_code == 401   # old sessions ended
    assert new_client().post("/api/auth/login", json={"email": "reset@example.com", "password": "a brand new phrase"}).status_code == 200


def test_reset_token_is_single_use_and_expires():
    new_client("tok@example.com")
    uid = uid_of("tok@example.com")
    t = auth.create_reset_token(uid)
    assert auth.consume_reset_token(t) == uid
    assert auth.consume_reset_token(t) is None
    t = auth.create_reset_token(uid)
    db.run("UPDATE password_resets SET expires=?", (time.time() - 1,))
    assert auth.consume_reset_token(t) is None


def test_admin_endpoints_and_provider_credit_are_admin_only():
    admin, user = new_client("boss@example.com"), new_client("user@example.com")
    assert admin.get("/api/auth/me").json()["isAdmin"] is True
    assert user.get("/api/admin/users").status_code == 403
    assert user.post("/api/providers/refresh").status_code == 403
    assert user.get("/api/admin/stats").status_code == 403
    rows = admin.get("/api/admin/users").json()
    assert {r["email"] for r in rows} == {"boss@example.com", "user@example.com"}
    target = uid_of("user@example.com")
    assert admin.patch(f"/api/admin/users/{target}", json={"monthlyCap": 7.5}).status_code == 200
    assert user.get("/api/auth/me").json()["monthCapUsd"] == 7.5
    assert admin.patch(f"/api/admin/users/{target}", json={"resetCap": True}).status_code == 200
    assert user.get("/api/auth/me").json()["monthCapUsd"] == config.DEFAULT_USER_MONTHLY_USD
    assert admin.patch(f"/api/admin/users/{target}", json={"disabled": True}).status_code == 200
    assert user.get("/api/chats").status_code == 401
    assert admin.patch(f"/api/admin/users/{uid_of('boss@example.com')}", json={"disabled": True}).status_code == 409
    assert admin.get("/api/admin/stats").json()["users"] == 2


def test_operator_credit_balance_is_hidden_from_users():
    from app.llm import registry
    registry.provider_status = {"openrouter": {"ok": True, "reason": "", "creditRemaining": 12.34, "creditLimit": 50}}
    admin, user = new_client("boss@example.com"), new_client("user@example.com")
    assert "creditRemaining" in admin.get("/api/config").json()["providers"]["openrouter"]
    assert "creditRemaining" not in user.get("/api/config").json()["providers"]["openrouter"]
    assert "12.34" not in user.get("/api/config").text


def test_production_refuses_unsafe_configuration(monkeypatch):
    from app.main import startup_problems
    monkeypatch.setattr(config, "PRODUCTION", True)
    monkeypatch.setattr(config, "AUTH_REQUIRED", False)
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "PUBLIC_URL", "")
    fatal, _ = startup_problems()
    assert len(fatal) == 3
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    monkeypatch.setattr(config, "PUBLIC_URL", "https://assistant.example.com")
    assert startup_problems()[0] == []


def test_single_user_mode_still_works_without_a_login(monkeypatch):
    monkeypatch.setattr(config, "AUTH_REQUIRED", False)
    c = TestClient(app, headers=ORIGIN)
    assert c.get("/api/chats").status_code == 200
    assert c.get("/api/auth/me").json()["email"] == "local"
    assert c.post("/api/auth/signup", json={"email": "z@example.com", "password": PASSWORD}).status_code == 404
