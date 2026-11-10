"""Spec regressions and deterministic fixture gates. Paid model accuracy is a separate live gate."""
import asyncio
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from app import files, llm, memory
from app.core import config, db
from app.core.costmeter import CostMeter
from app.llm import CallContext
from app.memory import portability
from app.memory.context import ContextOverflow

MODEL = "qwen/qwen3.7-flash"


def call_context(chat="c1", budget=.25):
    return CallContext(meter=CostMeter(budget), chat_id=chat, run_id="acceptance")


def table_chart_pdf(index=1):
    """Two real PDF pages: a ruled table and a vector bar chart, with a fixed expected fact."""
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawString(50, 800, f"Machine {index} maintenance table")
    rows = [("Part", "Capacity"), ("Gearbox", f"{index + 30} liters"), ("Pump", "12 liters")]
    for y in (740, 710, 680, 650):
        pdf.line(50, y, 350, y)
    for x in (50, 200, 350):
        pdf.line(x, 650, x, 740)
    for row, y in zip(rows, (720, 690, 660)):
        pdf.drawString(60, y, row[0]); pdf.drawString(210, y, row[1])
    pdf.showPage()
    pdf.drawString(50, 800, f"Machine {index} quarterly revenue chart")
    for x, height, label in ((70, 100, "Q1"), (160, 200, "Q2"), (250, 150, "Q3")):
        pdf.rect(x, 300, 50, height, fill=1)
        pdf.drawString(x, 280, label)
    pdf.save()
    return output.getvalue()


async def test_text_only_is_free_even_with_embeddings_on_and_zero_approval(fake_llm):
    db.set_setting("embeddings", True)
    memory.create_chat(chat_id="c1")
    uploaded = files.ingest("c1", "free.txt", b"A digital file has free direct text extraction.")
    result = await files.read_file("c1", uploaded["fingerprint"], "auto", text_only=True, max_cost=0)
    assert result["cost"] == 0 and fake_llm.calls == []
    assert db.one("SELECT COUNT(*) n FROM calls")["n"] == 0


async def test_reading_cache_is_stable_per_chat_and_last_detach_purges_disk(fake_llm):
    memory.create_chat(chat_id="a"); memory.create_chat(chat_id="b")
    first = files.ingest("a", "same.txt", b"An exact shared file.")
    files.ingest("b", "same.txt", b"An exact shared file.")
    fp = first["fingerprint"]
    await files.read_file("a", fp, "auto")
    await files.read_file("b", fp, "text")
    assert files.chat_readings("a")[0]["reader"] == "auto"
    assert files.chat_readings("b")[0]["reader"] == "text"
    path = Path(db.one("SELECT path FROM files WHERE fingerprint=?", (fp,))["path"])
    files.detach("a", fp)
    assert path.exists()
    files.detach("b", fp)
    assert not path.exists()
    for table in ("files", "readings", "chunks"):
        assert db.one(f"SELECT COUNT(*) n FROM {table} WHERE fingerprint=?", (fp,))["n"] == 0


async def test_compaction_preserves_more_than_sixty_details_with_their_original_relationships(fake_llm):
    memory.create_chat(chat_id="c1")
    text = "\n".join(f"Project-{i} has a budget of ${1000+i}." for i in range(80))
    memory.add_message("c1", "user", text)
    for _ in range(11):
        memory.add_message("c1", "assistant", "filler")
    fake_llm.on("compact:ledger", {"ops": []}).on("compact:summary", "A summary.").on("compact:redo", "A summary.")
    result = await memory.compact("c1", MODEL, call_context())
    kept = "\n".join(s["text"] for s in memory.active_summaries("c1"))
    assert result.ok and not memory.missing_items(text, kept)
    assert all(f"Project-{i} has a budget of ${1000+i}." in kept for i in range(80))
    assert db.one("SELECT content FROM messages WHERE chat_id=? AND seq=1", ("c1",))["content"] == text


async def test_context_refuses_overflow_and_sends_current_archived_user_only_once(fake_llm):
    memory.create_chat(chat_id="c1")
    memory.add_message("c1", "user", "Current message")
    memory.add_message("c1", "assistant", "")
    built = await memory.build("c1", "Current message", MODEL, with_files=False)
    assert sum(m["content"] == "Current message" for m in built.messages) == 1
    memory.update_settings({"windowCap": 4000})
    for _ in range(5):
        memory.add_message("c1", "user", "word " * 4000)
    with pytest.raises(ContextOverflow):
        await memory.build("c1", "Continue", MODEL, with_files=False)


async def test_fact_history_used_facts_and_unread_original_survive_encrypted_roundtrip(fake_llm):
    memory.create_chat(chat_id="source"); memory.create_chat(chat_id="consumer")
    old = memory.add_fact("My budget is $5", "original dated fact", "source", ts=1_000_000_000)
    current = memory.add_fact("My budget is $20", "changed dated fact", "source", replaces=old, ts=1_100_000_000, replaced_at=1_100_000_000)
    await memory.build("consumer", "What is my budget?", MODEL, with_files=False)
    up = files.ingest("consumer", "unread.txt", b"Original uploaded but not yet read.")
    blob = portability.build_export("consumer", include_files=True, password="correct horse")
    with pytest.raises(portability.ExportError, match="password"):
        await portability.import_chat(blob, "wrong password")
    restored = await portability.import_chat(blob, "correct horse")
    assert restored["facts"] == 2 and restored["files"] == 1
    assert db.one("SELECT replaced_by,ts,replaced_at FROM facts WHERE id=?", (old,))["replaced_by"] == current
    assert db.one("SELECT ts FROM facts WHERE id=?", (old,))["ts"] == 1_000_000_000
    assert files.chat_fingerprints(restored["chatId"]) == [up["fingerprint"]]
    assert len(memory.list_facts()) == 1  # Import does not revive or duplicate obsolete facts.


async def test_selected_pages_reuse_and_chart_images_survive_import(fake_llm):
    memory.create_chat(chat_id="c1")
    fake_llm.on("file:chart", "Q2 has the tallest bar, followed by Q3 and Q1.")
    uploaded = files.ingest("c1", "chart.pdf", table_chart_pdf())
    fp = uploaded["fingerprint"]
    assert uploaded["kinds"]["chart"] == 1 and uploaded["kinds"]["tables"] >= 1
    estimate = files.reading_estimate("c1", fp, "auto", pages=[1])
    result = await files.read_file("c1", fp, "auto", max_cost=estimate["total"], pages=[1])
    assert result["cost"] == 0
    assert files.file_status(fp)["readBefore"]["auto"]["complete"] is False
    estimate = files.reading_estimate("c1", fp, "auto", pages=[2])
    await files.read_file("c1", fp, "auto", max_cost=estimate["total"]+.001, pages=[2])
    assert files.file_status(fp)["readBefore"]["auto"]["complete"] is True
    repeated = await files.read_file("c1", fp, "auto", max_cost=0)
    assert repeated["reused"] and repeated["cost"] == 0
    archive = portability.build_export("c1", include_files=True)
    assert any(n.startswith("images/") for n in zipfile.ZipFile(io.BytesIO(archive)).namelist())
    restored = await portability.import_chat(archive)
    context = await files.file_context(restored["chatId"], "What does the chart show?", [], 32000, None, vision_model=True)
    assert context.images and "[Chart description]" in context.text and "chart.pdf p.2" in context.citations


async def test_deterministic_twenty_pdf_table_chart_retrieval_gate(fake_llm):
    """Real parsing/rasterization/indexing; mocked vision descriptions, not a live-model accuracy score."""
    correct = 0
    fake_llm.on("file:chart", "Q2 is highest, Q3 is second and Q1 is lowest.")
    for index in range(1, 21):
        chat = f"pdf-{index}"
        memory.create_chat(chat_id=chat)
        up = files.ingest(chat, f"manual-{index}.pdf", table_chart_pdf(index))
        assert up["kinds"]["tables"] >= 1 and up["kinds"]["chart"] == 1
        await files.read_file(chat, up["fingerprint"], "auto", max_cost=up["plans"]["auto"]["total"]+.001)
        table = await files.search_chunks(chat, "Gearbox Capacity liters")
        chart = await files.search_chunks(chat, "highest Q2 chart")
        correct += int(any(f"{index+30} liters" in c["text"] and c["page"] == 1 for c in table))
        correct += int(any("Q2 is highest" in c["text"] and c["page"] == 2 for c in chart))
    assert correct == 40


async def test_fifty_planted_facts_available_to_context_after_compaction_and_import(fake_llm):
    """Measures actual context retrieval for 50 facts; a separate live gate measures answer accuracy."""
    memory.create_chat(chat_id="facts")
    memory.update_settings({"windowCap": 32000})
    planted = {f"Vault-{i:03}": f"${5000+i}" for i in range(50)}
    for name, amount in planted.items():
        memory.add_message("facts", "user", f"The budget for {name} is {amount}.")
    for _ in range(12):
        memory.add_message("facts", "assistant", "filler text")
    fake_llm.on("compact:ledger", {"ops": []}).on("compact:summary", "The user supplied project budgets.").on("compact:redo", "The user supplied project budgets.")
    result = await memory.compact("facts", MODEL, call_context("facts"), target_percent=1)
    assert result.ok
    restored = await portability.import_chat(portability.build_export("facts"))
    recalled = 0
    for name, amount in planted.items():
        built = await memory.build(restored["chatId"], f"What is the budget for {name}?", MODEL, with_files=False)
        recalled += int(f"The budget for {name} is {amount}." in str(built.messages))
    assert recalled / len(planted) >= .95


async def test_new_chat_with_summary_keeps_source_archive_and_facts(fake_llm):
    memory.create_chat(chat_id="source")
    memory.add_message("source", "user", "My ticket is VX-9917, budget $430 and due date 2026-12-15.")
    fake_llm.on("compact:summary", "The user has an ongoing project.")
    forked = await memory.fork_with_summary("source", MODEL, call_context("source"))
    assert memory.get_chat("source") and forked["chatId"] != "source"
    built = await memory.build(forked["chatId"], "What is my ticket?", MODEL, with_files=False)
    assert "VX-9917" in str(built.messages) and "$430" in str(built.messages)


async def test_embeddings_meter_success_and_unknown_charges(monkeypatch):
    from app.files import search
    db.set_setting("embeddings", True)
    monkeypatch.setattr(search, "_embed_disabled_until", 0)
    class Response:
        status_code = 200
        def json(self):
            return {"data": [{"index": 0, "embedding": [1., 0.]}], "usage": {"prompt_tokens": 4, "cost": .000001}}
    class Client:
        async def post(self, *args, **kwargs):
            return Response()
    monkeypatch.setattr(llm, "client", lambda: Client())
    ctx = call_context()
    assert await search.embed_texts(["car price"], ctx=ctx)
    assert ctx.meter.calls == 1 and ctx.meter.usd == .000001
    class FailedClient:
        async def post(self, *args, **kwargs):
            raise TimeoutError("response lost after dispatch")
    monkeypatch.setattr(llm, "client", lambda: FailedClient())
    assert await search.embed_texts(["vehicle cost"], ctx=ctx) is None
    row = db.one("SELECT usage_estimated,completed,cost FROM calls ORDER BY id DESC LIMIT 1")
    assert row["usage_estimated"] and not row["completed"] and row["cost"] > 0
    assert ctx.meter.reserved == 0 and ctx.meter.calls == 2


async def test_explicit_reindex_requires_approval_and_reuses_completed_vectors(monkeypatch, fake_llm):
    from app.files import search
    from app.core import config
    memory.create_chat(chat_id="c1")
    upload = files.ingest("c1", "facts.txt", b"Ticket VX-9917 belongs to Dana. The budget is $430.")
    fp = upload["fingerprint"]
    await files.read_file("c1", fp, "text", max_cost=0)
    db.set_setting("embeddings", True)
    monkeypatch.setattr(config, "OPENROUTER_KEY", "test-key")
    monkeypatch.setattr(search, "_embed_disabled_until", 0)
    dispatched = []
    class Response:
        status_code = 200
        def json(self):
            return {"data": [{"index": 0, "embedding": [1., 0.]}], "usage": {"prompt_tokens": 15, "cost": .000001}}
    class Client:
        async def post(self, *args, **kwargs):
            dispatched.append(kwargs["json"])
            return Response()
    monkeypatch.setattr(llm, "client", lambda: Client())
    estimate = files.reindex_estimate("c1", fp)
    assert estimate["usd"] > 0 and estimate["chunks"] == 1
    with pytest.raises(files.FileError) as denied:
        await files.reindex_file("c1", fp, 0)
    assert denied.value.status == 402 and not dispatched
    result = await files.reindex_file("c1", fp, estimate["usd"])
    assert result["complete"] and result["cost"] == .000001 and len(dispatched) == 1
    again = await files.reindex_file("c1", fp, 0)
    assert again["complete"] and again["cost"] == 0 and len(dispatched) == 1


def serial_image():
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (650, 110), "white")
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 42) if font_path.exists() else ImageFont.load_default(size=42)
    ImageDraw.Draw(image).text((20, 25), "SERIAL ZX9917", fill="black", font=font)
    output = io.BytesIO(); image.save(output, "PNG")
    return output.getvalue()


def test_real_local_ocr_reads_a_generated_image_without_provider_calls():
    from app.files.ocr import local_read
    result = local_read(serial_image())
    assert "ZX9917" in result.replace(" ", "")
    assert db.one("SELECT COUNT(*) n FROM calls")["n"] == 0


async def test_office_embedded_pictures_are_read_without_losing_direct_text(monkeypatch, fake_llm):
    from app.files import ocr
    from docx import Document
    from pptx import Presentation
    from pptx.util import Inches
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as ExcelImage
    monkeypatch.setattr(ocr, "local_read", lambda _: "SERIAL ZX9917")
    image = serial_image()
    word = Document(); word.add_paragraph("Direct document contract ABC-123"); word.add_picture(io.BytesIO(image))
    output = io.BytesIO(); word.save(output)
    fixtures = [("word.docx", output.getvalue(), "ABC-123")]
    slides = Presentation(); slide = slides.slides.add_slide(slides.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1)).text = "Direct slide project PPT-456"
    slide.shapes.add_picture(io.BytesIO(image), Inches(1), Inches(2))
    output = io.BytesIO(); slides.save(output)
    fixtures.append(("slides.pptx", output.getvalue(), "PPT-456"))
    workbook = Workbook(); sheet = workbook.active; sheet["A1"] = "Direct cells XLS-789"; sheet.add_image(ExcelImage(io.BytesIO(image)), "A3")
    output = io.BytesIO(); workbook.save(output)
    fixtures.append(("sheet.xlsx", output.getvalue(), "XLS-789"))
    for i, (name, data, direct) in enumerate(fixtures):
        chat = f"office-{i}"
        memory.create_chat(chat_id=chat)
        up = files.ingest(chat, name, data)
        assert up["kinds"]["scan"] >= 1
        read = await files.read_file(chat, up["fingerprint"], "local", max_cost=0)
        assert read["cost"] == 0
        context = await files.file_context(chat, "What is the serial and direct text?", [], 32000, None)
        assert direct in context.text and "ZX9917" in context.text
