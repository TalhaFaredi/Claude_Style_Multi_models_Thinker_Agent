r"""Append the versioned Markdown addendum to the original specification PDF.

Run from the repository root with the backend virtualenv:
    .\backend\.venv\Scripts\python.exe scripts\build_spec_v2.py

The original PDF is read only. This script writes a separate v2 document.
"""
from __future__ import annotations

import html
import io
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "Multi-Mode_AI_Assistant_Complete_Spec (1).pdf"
ADDENDUM = ROOT / "spec-audit" / "SPEC-ADDENDUM.md"
OUTPUT = ROOT / "Multi-Mode_AI_Assistant_Complete_Spec_v2.pdf"


def fonts() -> tuple[str, str]:
    candidates = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("SpecBody", str(regular)))
            pdfmetrics.registerFont(TTFont("SpecBold", str(bold)))
            pdfmetrics.registerFontFamily("SpecBody", normal="SpecBody", bold="SpecBold")
            return "SpecBody", "SpecBold"
    return "Helvetica", "Helvetica-Bold"


def markup(text: str) -> str:
    escaped = html.escape(text.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    return escaped.replace("`", "")


def render_addendum(source: str, heading_text: str = "Multi-Mode AI Assistant - Specification v2 Addendum") -> bytes:
    regular, bold = fonts()
    body = ParagraphStyle("Body", fontName=regular, fontSize=9, leading=13, spaceAfter=5)
    title = ParagraphStyle("Title", parent=body, fontName=bold, fontSize=17, leading=22, alignment=TA_CENTER, spaceAfter=18)
    heading = ParagraphStyle("Heading", parent=body, fontName=bold, fontSize=12, leading=16, spaceBefore=12, spaceAfter=7)
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=11)
    out: list = [Paragraph(heading_text, title)]
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            out.append(Spacer(1, 5))
        elif line.startswith("# "):
            out.append(Paragraph(markup(line[2:]), heading))
        elif line.startswith("## ") or line.startswith("### "):
            out.append(Paragraph(markup(line.lstrip("# ")), heading))
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
                    rows.append([Paragraph(markup(cell), small) for cell in cells])
                i += 1
            i -= 1
            if rows:
                width = (A4[0] - 90) / len(rows[0])
                table = Table(rows, colWidths=[width] * len(rows[0]), repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#b6b6b6")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4ef")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]))
                out.append(table)
        elif line.startswith(('- ', '* ')):
            out.append(Paragraph("&#8226; " + markup(line[2:]), body))
        elif re.match(r"\d+\.\s", line):
            out.append(Paragraph(markup(line), body))
        elif line.startswith('```'):
            pass
        else:
            out.append(Paragraph(markup(line), body))
        i += 1
    target = io.BytesIO()
    SimpleDocTemplate(target, pagesize=A4, leftMargin=45, rightMargin=45, topMargin=45, bottomMargin=45,
                      title="Multi-Mode AI Assistant - v2 Addendum").build(out)
    return target.getvalue()


def main() -> None:
    if not ORIGINAL.is_file() or not ADDENDUM.is_file():
        raise SystemExit("The original specification PDF and spec-audit/SPEC-ADDENDUM.md are required.")
    source = PdfReader(str(ORIGINAL))
    appendix = PdfReader(io.BytesIO(render_addendum(ADDENDUM.read_text(encoding="utf-8"))))
    writer = PdfWriter()
    writer.append_pages_from_reader(source)
    writer.append_pages_from_reader(appendix)
    writer.add_metadata({"/Title": "Multi-Mode AI Assistant Complete Specification v2", "/Subject": "Original specification plus versioned model, thinking, prompt and pricing addendum"})
    with OUTPUT.open("wb") as handle:
        writer.write(handle)
    print(f"Wrote {OUTPUT.name}: {len(source.pages)} original pages + {len(appendix.pages)} addendum pages")


if __name__ == "__main__":
    main()
