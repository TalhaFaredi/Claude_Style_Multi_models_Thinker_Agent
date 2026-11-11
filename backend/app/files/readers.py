"""Free, direct reading of every format that has a text layer (C23, C24): PDF, Word, Excel, text and code.
Returns (text, number of embedded images) per page."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from app.files.common import IMAGE_EXT, PAGE_CHARS, TEXT_EXT, FileError


def _pdf_pages(data: bytes) -> list[tuple[str, int]]:
    return [(p["text"], p["images"]) for p in pdf_layout(data)]


def pdf_layout(data: bytes) -> list[dict]:
    """Layout-aware free parsing: preserve table cells and detect vector drawings as visual content."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as document:
            out = []
            for page in document.pages:
                tables = page.extract_tables()
                text = page.extract_text(layout=False) or ""
                if tables:
                    rendered = []
                    for table in tables:
                        rows = [[str(cell or "").replace("\n", " ") for cell in row] for row in table]
                        if not rows:
                            continue
                        rendered.append("\n".join(" | ".join(row) for row in rows))
                    text += "\n\n" + "\n\n".join(rendered)
                drawings = bool(page.curves or (len(page.rects) >= 2 and not tables))
                out.append({"text": text, "images": len(page.images), "chart": drawings or bool(page.images), "table": bool(tables)})
            return out
    except Exception:
        pass
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise FileError("This PDF is password protected", 422)
    except FileError:
        raise
    except Exception as e:
        raise FileError(f"Could not read this PDF: {type(e).__name__}", 422)
    out = []
    for p in reader.pages:
        try:
            text = p.extract_text() or ""
        except Exception:
            text = ""
        try:
            n_img = len(p.images)
        except Exception:
            n_img = 0
        # A content-stream fallback still detects vector path paint operations without a native renderer.
        try:
            from pypdf.generic import ContentStream
            ops = ContentStream(p.get_contents(), reader).operations
            drawn = sum(op in (b"re", b"c", b"v", b"y") for _, op in ops) >= 2
        except Exception:
            drawn = False
        out.append({"text": text, "images": n_img, "chart": drawn or n_img > 0, "table": False})
    return out


def _split_pages(text: str) -> list[str]:
    """Cut page-less text into ~3,000-character pages at paragraph breaks."""
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if len(cur) + len(para) > PAGE_CHARS and cur:
            parts.append(cur)
            cur = ""
        cur += para + "\n\n"
    if cur.strip():
        parts.append(cur)
    return parts or [""]


def _docx_pages(data: bytes) -> list[tuple[str, int]]:
    import docx
    d = docx.Document(io.BytesIO(data))
    lines = []
    for p in d.paragraphs:
        if p.text.strip():
            prefix = "# " if (p.style and p.style.name.lower().startswith("heading")) else ""
            lines.append(prefix + p.text)
    for t in d.tables:
        for row in t.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
        lines.append("")
    n_img = len(d.inline_shapes)
    return [(t, n_img if i == 0 else 0) for i, t in enumerate(_split_pages("\n".join(lines)))]


def _xlsx_pages(data: bytes) -> list[tuple[str, int]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    pages = []
    for ws in wb.worksheets:
        rows = [" | ".join("" if v is None else str(v) for v in row) for row in ws.iter_rows(values_only=True)]
        pages.append((f"# Sheet: {ws.title}\n" + "\n".join(r for r in rows if r.strip(" |")), len(ws._images)))
    return pages or [("", 0)]


def _pptx_pages(data: bytes) -> list[tuple[str, int]]:
    from pptx import Presentation
    presentation = Presentation(io.BytesIO(data))
    result = []
    for slide in presentation.slides:
        lines, images = [], 0
        for shape in slide.shapes:
            if shape.shape_type == 13:
                images += 1
            if shape.has_text_frame:
                lines.extend(p.text for p in shape.text_frame.paragraphs)
            if shape.has_table:
                lines.extend(" | ".join(c.text for c in row.cells) for row in shape.table.rows)
            if shape.has_chart:
                chart = shape.chart
                for series in chart.series:
                    lines.append(f"Chart series {series.name}: " + ", ".join(str(v) for v in series.values))
                for plot in chart.plots:
                    lines.append("Chart categories: " + ", ".join(c.label for c in plot.categories))
        result.append(("\n".join(lines), images))
    return result or [("", 0)]


def embedded_images(name: str, data: bytes, page_no: int) -> list[bytes]:
    ext = Path(name).suffix.lower()
    if ext == ".docx":
        if page_no != 1:
            return []
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return [archive.read(n) for n in archive.namelist() if n.startswith("word/media/")]
    if ext == ".pptx":
        from pptx import Presentation
        slide = Presentation(io.BytesIO(data)).slides[page_no - 1]
        return [s.image.blob for s in slide.shapes if s.shape_type == 13]
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        return [img._data() for img in workbook.worksheets[page_no - 1]._images]
    return []


def decode_text(data: bytes) -> str:
    """Text and CSV files saved on Windows are often UTF-16 or Windows-1252, not UTF-8. Decoding those as UTF-8
    turned every accented letter into a replacement mark and the page was then treated as an unreadable scan."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    if b"\x00" in data:   # real binary under a text extension: keep the marks so the page is flagged
        return data.decode("utf-8", "replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", "replace")


def extract_text_pages(name: str, data: bytes) -> list[tuple[str, int]]:
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        return _pdf_pages(data)
    if ext == ".docx":
        return _docx_pages(data)
    if ext == ".pptx":
        return _pptx_pages(data)
    if ext in (".xlsx", ".xlsm"):
        return _xlsx_pages(data)
    if ext in TEXT_EXT:
        return [(t, 0) for t in _split_pages(decode_text(data))]
    if ext in IMAGE_EXT:
        return [("", 1)]
    raise FileError(f"Unsupported file type {ext or '(none)'}", 415)
