"""No data leakage: keys never reach logs or answers, chats are isolated, deletes are real."""
import io
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import files, memory, output
from app.core import config, db
from app.core.privacy import RedactingFilter
from app.llm import registry
from app.llm.client import _body

FAKE_KEY = "sk-or-v1-" + "b" * 48


def test_logs_never_contain_a_provider_key(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_KEY", FAKE_KEY)
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(RedactingFilter())
    log = logging.getLogger("leak-test")
    log.addHandler(handler)
    try:
        log.error("calling with %s", FAKE_KEY)
        try:
            raise RuntimeError(f"Authorization: Bearer {FAKE_KEY}")
        except RuntimeError:
            log.exception("failed")
    finally:
        log.removeHandler(handler)
    assert FAKE_KEY not in buf.getvalue() and "[redacted]" in buf.getvalue()


def test_openrouter_requests_ask_for_providers_that_do_not_store_prompts():
    info = registry.get("qwen/qwen3.7-flash")
    body = _body(info, [{"role": "user", "content": "hi"}], stream=False, tools=None, temperature=0.5, max_tokens=10, thinking="off")
    assert body["provider"] == {"data_collection": "deny"}
    memory.update_settings({"privateProviders": False})
    body = _body(info, [{"role": "user", "content": "hi"}], stream=False, tools=None, temperature=0.5, max_tokens=10, thinking="off")
    assert "provider" not in body


def test_retry_cannot_delete_a_message_from_another_chat():
    memory.create_chat(chat_id="a")
    other = memory.add_message("b", "user", "private message in chat b")
    assert memory.delete_message("a", other["id"]) is False
    assert db.one("SELECT 1 FROM messages WHERE id=?", (other["id"],)) is not None


async def test_a_temporary_chat_does_not_read_long_term_memory(fake_llm):
    memory.add_fact("The user's salary is 91,000", "chat", None)
    memory.create_chat(chat_id="normal")
    memory.create_chat(chat_id="temp", temp=True)
    normal = await memory.build("normal", "what is my salary?", "qwen/qwen3.7-flash", with_files=False)
    temp = await memory.build("temp", "what is my salary?", "qwen/qwen3.7-flash", with_files=False)
    assert "91,000" in str(normal.messages) and "91,000" not in str(temp.messages)


def test_deleting_a_fact_removes_its_text():
    fid = memory.add_fact("Lives at 12 Elm Street", "chat", None)
    memory.delete_fact(fid)
    assert db.one("SELECT COUNT(*) n FROM facts WHERE text LIKE '%Elm Street%'")["n"] == 0
    assert db.one("SELECT COUNT(*) n FROM fact_fts WHERE text LIKE '%Elm Street%'")["n"] == 0


async def test_a_chat_cannot_read_a_file_attached_only_to_another_chat(fake_llm):
    memory.create_chat(chat_id="owner")
    up = files.ingest("owner", "notes.txt", b"secret plan: launch on 2026-12-01")
    with pytest.raises(files.FileError) as err:
        await files.read_file("stranger", up["fingerprint"], "auto")
    assert err.value.status == 404
    await files.read_file("owner", up["fingerprint"], "auto")
    assert await files.search_chunks("stranger", "secret plan launch") == []
    assert await files.search_chunks("owner", "secret plan launch")


async def test_deleting_a_chat_removes_its_outputs_and_files_no_other_chat_uses(fake_llm):
    memory.create_chat(chat_id="gone")
    memory.create_chat(chat_id="kept")
    memory.add_message("gone", "user", "hello")
    only = files.ingest("gone", "only.txt", b"only in the deleted chat " * 20)
    shared = files.ingest("gone", "shared.txt", b"shared between two chats " * 20)
    files.ingest("kept", "shared.txt", b"shared between two chats " * 20)
    await files.read_file("gone", only["fingerprint"], "auto")
    art = output.build_artifact("gone", "Report", "# Report\n\ntext", "md")
    art_path = Path(db.one("SELECT path FROM artifacts WHERE id=?", (art["id"],))["path"])
    only_path = Path(db.one("SELECT path FROM files WHERE fingerprint=?", (only["fingerprint"],))["path"])
    assert art_path.exists() and only_path.exists()

    out = memory.delete_chat("gone", delete_memories=True)
    assert out["filesRemoved"] == 1 and out["outputsRemoved"] == 1
    assert not art_path.exists() and output.get_artifact(art["id"]) is None
    assert not only_path.exists()
    for table in ("files", "readings", "chunks"):
        assert db.one(f"SELECT COUNT(*) n FROM {table} WHERE fingerprint=?", (only["fingerprint"],))["n"] == 0
    assert db.one("SELECT COUNT(*) n FROM files WHERE fingerprint=?", (shared["fingerprint"],))["n"] == 1   # still used by "kept"


def test_export_password_is_read_from_a_header_and_never_faked():
    from app.main import app
    memory.create_chat(chat_id="c1")
    memory.add_message("c1", "user", "hi")
    c = TestClient(app)
    encrypted = c.get("/api/chats/c1/export", headers={"X-Export-Password": "pw"})
    assert encrypted.status_code == 200
    import pyzipper
    archive = pyzipper.AESZipFile(io.BytesIO(encrypted.content))
    with pytest.raises(RuntimeError):
        archive.read("messages.jsonl")
    archive.setpassword(b"pw")
    assert b'"hi"' in archive.read("messages.jsonl")
    assert c.get("/api/chats/c1/export").status_code == 200


def test_artifact_ids_are_long_random_and_validated():
    art = output.build_artifact(None, "x", "y", "txt")
    assert len(art["id"]) == 32
    assert output.get_artifact("../../etc/passwd") is None
