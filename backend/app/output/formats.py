"""Markdown -> file renderers: PDF (reportlab) and a static web page. All model text is escaped."""
from __future__ import annotations

import html
import io
import re
import json
import os
import textwrap
from pathlib import Path

_HEADING = re.compile(r"^(#{1,3})\s+(.*)")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)")
_RULE = re.compile(r"\s*(-{3,}|\*{3,}|_{3,})\s*")   # Markdown horizontal rule


def font_path() -> Path | None:
    candidates = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgun.ttf",
                  Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    return next((p for p in candidates if p.is_file()), None)


def _inline(s: str) -> str:
    """Escape, then turn **bold**, *italic* and `code` into reportlab's mini-markup."""
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", s)
    return re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', s)


# Type sizes tried, largest first, when a PDF must fit a requested page count. 0.78 keeps body text near 8 pt.
PDF_FIT_SCALES = (1.0, 0.92, 0.85, 0.78)
_PAGES_ASKED = re.compile(r"\b(\d{1,3})\s*[- ]\s*pages?\b", re.I)


def requested_pages(goal: str, fmt: str) -> int | None:
    """'Make a 2-page PDF report ...' -> 2. Only for PDF output."""
    m = _PAGES_ASKED.search(goal or "") if fmt == "pdf" else None
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def fit_pdf(title: str, markdown: str, pages: int | None) -> bytes:
    """Render; if a page count was requested and the text runs over, shrink the type step by step to fit.
    Content is never cut here: if even the smallest size runs over, the caller's page check reports it."""
    data = to_pdf(title, markdown)
    if not pages:
        return data
    for scale in PDF_FIT_SCALES[1:]:
        if pdf_pages(data) <= pages:
            break
        data = to_pdf(title, markdown, scale)
    return data


def to_pdf(title: str, markdown: str, scale: float = 1.0) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors

    ss = getSampleStyleSheet()
    if path := font_path():
        if "AssistantUnicode" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("AssistantUnicode", str(path)))
            pdfmetrics.registerFontFamily("AssistantUnicode", normal="AssistantUnicode", bold="AssistantUnicode", italic="AssistantUnicode", boldItalic="AssistantUnicode")
        for style in ss.byName.values():
            style.fontName = "AssistantUnicode"
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=10.5 * scale, leading=15 * scale, spaceAfter=6 * scale)
    h1, h2, h3 = (ParagraphStyle(n, parent=ss[n], fontSize=ss[n].fontSize * scale, leading=ss[n].leading * scale,
                                 spaceBefore=10 * scale, spaceAfter=6 * scale) for n in ("Heading1", "Heading2", "Heading3"))
    buf = io.BytesIO()
    margin = (20 if scale >= 1 else 16) * mm
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin * 0.9, bottomMargin=margin * 0.9, title=title)
    story: list = []
    bullets: list[str] = []
    table_rows: list[list[str]] = []

    def flush():
        if bullets:
            story.append(ListFlowable([ListItem(Paragraph(_inline(b), body)) for b in bullets], bulletType="bullet", leftIndent=14))
            bullets.clear()

    def flush_table():
        if not table_rows:
            return
        width = max(len(row) for row in table_rows)
        cells = [[Paragraph(_inline(value), body) for value in row + [""] * (width - len(row))] for row in table_rows]
        table = Table(cells, colWidths=[170 * mm / width] * width, repeatRows=1)
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf1ec")), ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
        story.append(table)
        table_rows.clear()

    for line in markdown.splitlines():
        s = line.rstrip()
        if re.fullmatch(r"\s*<!--\s*page\s*break\s*-->\s*", s, re.I):
            flush()
            flush_table()
            story.append(PageBreak())
            continue
        if not s.strip():
            flush_table()   # a blank line ends a table; paragraph spacing already separates blocks,
            continue        # and a loose list (blank lines between bullets) stays one list
        if _RULE.fullmatch(s):
            flush()
            flush_table()
            story.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#c9c6bb"), spaceBefore=4 * scale, spaceAfter=6 * scale))
            continue
        if "|" in s and len(s.strip().strip("|").split("|")) >= 2:
            flush()
            row = [cell.strip() for cell in s.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in row):
                table_rows.append(row)
            continue
        flush_table()
        b = _BULLET.match(s) or _NUMBERED.match(s)
        if b:
            bullets.append(b.group(1))
            continue
        flush()
        m = _HEADING.match(s)
        if m:
            story.append(Paragraph(_inline(m.group(2)), {1: h1, 2: h2, 3: h3}[len(m.group(1))]))
        else:
            story.append(Paragraph(_inline(s), body))
    flush()
    flush_table()
    doc.build(story or [Paragraph("(empty)", body)])
    return buf.getvalue()


def to_png(title: str, content: str) -> bytes:
    """Render a bounded drawing specification or a plain-text document card; never execute code."""
    from PIL import Image, ImageColor, ImageDraw, ImageFont

    spec = None
    if content.lstrip().startswith("{"):
        spec = json.loads(content)
        if not isinstance(spec, dict):
            raise ValueError("PNG drawing must be an object")
    width = max(256, min(3000, int((spec or {}).get("width", 1200))))
    height = max(256, min(3000, int((spec or {}).get("height", 1600))))

    def color(value, default):
        try:
            return ImageColor.getrgb(str(value))
        except ValueError:
            return default

    image = Image.new("RGB", (width, height), color((spec or {}).get("background", "white"), "white"))
    draw = ImageDraw.Draw(image)
    path = font_path()

    def font(size):
        return ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size=size)

    if spec is None:
        draw.text((50, 40), title[:100], fill="#183a2a", font=font(38))
        y = 110
        for paragraph in content.splitlines():
            for line in textwrap.wrap(paragraph, width=max(15, (width - 100) // 16)) or [""]:
                if y > height - 50:
                    raise ValueError("The PNG text does not fit; shorten the document or use PDF")
                draw.text((50, y), line, fill="#191919", font=font(26))
                y += 36
    else:
        elements = spec.get("elements", [])
        if not isinstance(elements, list) or len(elements) > 1000:
            raise ValueError("PNG requires at most 1000 drawing elements")
        for element in elements:
            if not isinstance(element, dict):
                raise ValueError("Invalid PNG drawing element")
            kind = element.get("type")
            x, y = int(element.get("x", 0)), int(element.get("y", 0))
            x2, y2 = int(element.get("x2", x + 100)), int(element.get("y2", y + 100))
            if any(abs(v) > 10000 for v in (x, y, x2, y2)) or x2 < x or y2 < y:
                raise ValueError("Invalid PNG coordinates")
            fill, stroke = color(element.get("fill", "#163a28"), "black"), color(element.get("stroke", "black"), "black")
            if kind == "text":
                draw.multiline_text((x, y), str(element.get("text", ""))[:2000], fill=fill, font=font(max(8, min(160, int(element.get("size", 26))))))
            elif kind == "rect":
                draw.rectangle((x, y, x2, y2), fill=fill, outline=stroke, width=2)
            elif kind == "ellipse":
                draw.ellipse((x, y, x2, y2), fill=fill, outline=stroke, width=2)
            elif kind == "line":
                draw.line((x, y, x2, y2), fill=stroke, width=max(1, min(20, int(element.get("width", 2)))))
            else:
                raise ValueError("Unsupported PNG element type")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def to_html(title: str, markdown: str) -> str:
    """A static page: every piece of model text is escaped, so no script can come from the model."""
    out, in_list = [], False
    for line in markdown.splitlines():
        s = line.rstrip()
        m, b = _HEADING.match(s), _BULLET.match(s)
        if b and not in_list:
            out.append("<ul>")
            in_list = True
        if not b and in_list:
            out.append("</ul>")
            in_list = False
        if b:
            out.append(f"<li>{html.escape(b.group(1))}</li>")
        elif _RULE.fullmatch(s):
            out.append("<hr>")
        elif m:
            n = len(m.group(1))
            out.append(f"<h{n}>{html.escape(m.group(2))}</h{n}>")
        elif s.strip():
            out.append(f"<p>{html.escape(s)}</p>")
    if in_list:
        out.append("</ul>")
    return (f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>body{{font:16px/1.6 system-ui;max-width:760px;margin:2rem auto;padding:0 1rem;color:#141413}}</style>"
            f"<body>{''.join(out)}</body></html>")


def pdf_pages(data: bytes) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return 1
