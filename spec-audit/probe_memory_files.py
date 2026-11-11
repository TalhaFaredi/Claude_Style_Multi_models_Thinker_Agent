"""Offline audit probes. Isolated in-memory DB, no provider calls or user data writes."""
from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATA_DIR"] = str(ROOT / "spec-audit" / "probe-data")
sys.path.insert(0, str(ROOT / "backend"))

from app import files, llm, memory
from app.core import db
from app.core.costmeter import CostMeter
from app.llm import CallContext, ChatResult, Usage, registry
from app.memory import portability

calls = []

async def fake_complete(model, messages, *, stage, ctx=None, **kwargs):
    calls.append(stage)
    text = json.dumps({"ops": []}) if stage == "compact:ledger" else "A short summary."
    if ctx and ctx.meter:
        ctx.meter.add(stage, 0.0001, 100, 20)
    return ChatResult(text=text, usage=Usage(prompt=100, completion=20, cost=0.0001), model=model)

llm.complete = fake_complete

def reset():
    db.reset_for_tests()
    db.set_setting("embeddings", False)
    registry._build([])
    calls.clear()

async def main():
    results = {}
    reset()
    memory.create_chat(chat_id="free")
    up = files.ingest("free", "notes.txt", b"The meeting is on Tuesday. " * 12)
    read = await files.read_file("free", up["fingerprint"], "text", text_only=True, max_cost=0)
    results["free_text_read"] = {"estimate": up["plans"]["text"]["total"], "approved": 0, "actual_mock_cost": read["cost"], "model_calls": list(calls)}

    reset()
    memory.create_chat(chat_id="facts")
    old = memory.add_fact("Budget is $5", "original", "facts")
    memory.add_fact("Budget is $20", "updated", "facts", replaces=old)
    db.run("UPDATE facts SET ts=1000000000 WHERE chat_id=?", ("facts",))
    exported = portability.build_export("facts")
    imported = await portability.import_chat(exported)
    fact_rows = [dict(r) for r in db.q("SELECT text,ts,replaced_by,replaced_at FROM facts WHERE chat_id=?", (imported["chatId"],))]
    results["fact_roundtrip"] = {"original_timestamp": 1000000000, "restored": fact_rows}

    reset()
    memory.create_chat(chat_id="source")
    memory.create_chat(chat_id="consumer")
    memory.add_fact("My preferred editor is Vim", "source", "source")
    built = await memory.build("consumer", "What is my preferred editor?", "qwen/qwen3.7-flash", with_files=False)
    archive = zipfile.ZipFile(io.BytesIO(portability.build_export("consumer")))
    results["used_memory_export"] = {"fact_in_consumer_prompt": "Vim" in str(built.messages), "exported_facts": json.loads(archive.read("facts.json"))}

    reset()
    memory.create_chat(chat_id="unread")
    files.ingest("unread", "unread.txt", b"An uploaded original that has not been read.")
    exported = portability.build_export("unread", include_files=True)
    archive = zipfile.ZipFile(io.BytesIO(exported))
    imported = await portability.import_chat(exported)
    results["unread_file_roundtrip"] = {"original_in_zip": any(n.startswith("files/") for n in archive.namelist()), "restored_files": imported["files"]}

    reset()
    memory.create_chat(chat_id="detached")
    up = files.ingest("detached", "removed.txt", b"A file removed before deleting its chat.")
    await files.read_file("detached", up["fingerprint"], "text")
    files.detach("detached", up["fingerprint"])
    memory.delete_chat("detached", delete_memories=True)
    results["detached_then_deleted"] = {
        "file_still_stored": db.one("SELECT 1 FROM files WHERE fingerprint=?", (up["fingerprint"],)) is not None,
        "reading_still_cached": db.one("SELECT 1 FROM readings WHERE fingerprint=?", (up["fingerprint"],)) is not None,
        "chunks_still_indexed": db.one("SELECT 1 FROM chunks WHERE fingerprint=?", (up["fingerprint"],)) is not None,
    }

    reset()
    memory.create_chat(chat_id="rich")
    memory.create_chat(chat_id="text")
    registry.provider_status = {"openrouter": {"ok": True, "reason": ""}, "nvidia": {"ok": False, "reason": "offline probe"}}
    registry._apply_status()
    image_data = b"a synthetic image used only with a fake vision model"
    up = files.ingest("rich", "scan.png", image_data)
    files.ingest("text", "scan.png", image_data)
    await files.read_file("rich", up["fingerprint"], "auto")
    before = files.chat_readings("rich")[0]["reader"]
    await files.read_file("text", up["fingerprint"], "text")
    after = files.chat_readings("rich")[0]["reader"]
    results["other_chat_changes_reader"] = {"original_chat_reader_before": before, "original_chat_reader_after_other_chat_text_read": after, "original_chat_file_tokens": files.total_file_tokens("rich")}

    reset()
    memory.create_chat(chat_id="compact")
    amounts = " ".join(f"${n}" for n in range(1001, 1081))
    memory.add_message("compact", "user", "Budgets: " + amounts)
    for _ in range(11):
        memory.add_message("compact", "assistant", "A filler message.")
    res = await memory.compact("compact", "qwen/qwen3.7-flash", CallContext(meter=CostMeter(budget=1), chat_id="compact"))
    summary = db.one("SELECT text FROM summaries WHERE chat_id=?", ("compact",))["text"]
    missing = memory.missing_items(amounts, summary)
    results["compaction_critical_cap"] = {"reported_ok": res.ok, "reported_preserved_extra": res.preserved_extra, "lost_exact_amounts": missing, "lost_count": len(missing)}

    reset()
    memory.create_chat(chat_id="overflow")
    memory.update_settings({"windowCap": 4000})
    for _ in range(5):
        memory.add_message("overflow", "user", "word " * 4000)
    built = await memory.build("overflow", "Please continue", "qwen/qwen3.7-flash", with_files=False)
    res = await memory.compact("overflow", "qwen/qwen3.7-flash", CallContext(meter=CostMeter(budget=1), chat_id="overflow"))
    results["context_overflow"] = {"window": built.window, "usable": built.usable, "built_tokens": built.tokens, "percent": built.percent, "compaction_ok": res.ok, "reason": res.reason}

    reset()
    from reportlab.pdfgen import canvas
    from app.files.analysis import analyze
    from app.files.vision import page_image
    pdf_bytes = io.BytesIO()
    graph = canvas.Canvas(pdf_bytes)
    graph.drawString(50, 780, "Quarterly revenue chart for our sales divisions")
    for x, height, label in ((80, 100, "Q1"), (160, 160, "Q2"), (240, 220, "Q3")):
        graph.rect(x, 200, 50, height, fill=1)
        graph.drawString(x, 180, label)
    graph.save()
    graph_data = pdf_bytes.getvalue()
    results["vector_chart_pdf"] = {"analyzed": [p.to_dict() for p in analyze("chart.pdf", graph_data)], "has_page_image": page_image(graph_data, "chart.pdf", 1) is not None}

    reset()
    memory.create_chat(chat_id="office")
    for name in ("slides.pptx", "legacy.doc", "legacy.xls"):
        try:
            files.ingest("office", name, b"x")
        except files.FileError as e:
            results[name] = {"status": e.status, "message": str(e)}

    output = json.dumps(results, indent=2)
    (ROOT / "spec-audit" / "memory-files-probe-results.json").write_text(output, encoding="utf-8")
    print(output)

if __name__ == "__main__":
    asyncio.run(main())
