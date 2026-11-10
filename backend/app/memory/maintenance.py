"""Idle index maintenance; never deletes archived words or remembered facts."""
from app.core import db


def idle_cleanup() -> dict:
    """Remove only dangling search entries left by an interrupted write, not user content."""
    with db.tx() as c:
        before = c.total_changes
        c.execute("DELETE FROM msg_fts WHERE msg_id NOT IN (SELECT id FROM messages)")
        c.execute("DELETE FROM fact_fts WHERE fact_id NOT IN (SELECT id FROM facts)")
        c.execute("DELETE FROM chunk_fts WHERE chunk_id NOT IN (SELECT id FROM chunks)")
        c.execute("DELETE FROM chat_facts WHERE fact_id NOT IN (SELECT id FROM facts) OR chat_id NOT IN (SELECT id FROM chats)")
        removed = c.total_changes - before
    return {"danglingIndexEntriesRemoved": removed}
