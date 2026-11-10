"""Memory and context (spec Part 2 sections 6 to 8). Storage keeps everything; the Context Builder rebuilds the
window before every turn; the Memory Writer updates storage after each reply.

    settings.py     user settings with safe defaults; who may use long-term memory (C41)
    archive.py      chats and every message word for word (+ delete everything, C42)
    facts.py        long-term memory: dated facts with sources; replaced, never silently lost (C39)
    ledger.py       numbered session ledger, changed only by small edits
    recall.py       "as I said last week" -> original messages (C40)
    context.py      Context Builder, context meter, calibration (C3, C34 to C38)
    compaction.py   checked auto-compaction at 95% (C37)
    portability.py  export and import (C43, C44)
"""
from app.memory.archive import (add_message, create_chat, delete_chat, delete_message, ensure_chat, get_chat, list_chats, rate_message,
                                rename_chat, ui_messages, update_message)
from app.memory.compaction import CompactResult, compact, critical_items, missing_items, fork_with_summary
from app.memory.context import Built, ContextOverflow, active_summaries, build, calibrate, checker_context, level_for, meter, window_for
from app.memory.facts import add_fact, delete_fact, list_facts, relevant_facts, write_turn_memory
from app.memory.ledger import ledger_apply, ledger_items
from app.memory.recall import recall_originals
from app.memory.settings import DEFAULT_SETTINGS, get_settings, long_memory_on, update_settings
from app.memory.maintenance import idle_cleanup

__all__ = ["add_message", "create_chat", "delete_chat", "delete_message", "ensure_chat", "get_chat", "list_chats", "rate_message", "rename_chat",
           "ui_messages", "update_message", "CompactResult", "compact", "critical_items", "missing_items", "Built", "active_summaries", "build",
           "calibrate", "checker_context", "level_for", "meter", "window_for", "add_fact", "delete_fact", "list_facts", "relevant_facts", "write_turn_memory",
           "ledger_apply", "ledger_items", "recall_originals", "DEFAULT_SETTINGS", "get_settings", "long_memory_on", "update_settings"]
