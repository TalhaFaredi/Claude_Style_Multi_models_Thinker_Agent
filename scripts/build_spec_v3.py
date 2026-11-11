r"""Build the v3 specification: original PDF + v2 addendum + v3 addendum, in that order.

Run from the repository root with the backend virtualenv:
    .\backend\.venv\Scripts\python.exe scripts\build_spec_v3.py

The original PDF and the v2 PDF are read only; this writes a separate v3 document.
"""
from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from build_spec_v2 import ADDENDUM as ADDENDUM_V2, ORIGINAL, ROOT, render_addendum

ADDENDUM_V3 = ROOT / "spec-audit" / "SPEC-ADDENDUM-v3.md"
OUTPUT = ROOT / "Multi-Mode_AI_Assistant_Complete_Spec_v3.pdf"


def main() -> None:
    for path in (ORIGINAL, ADDENDUM_V2, ADDENDUM_V3):
        if not path.is_file():
            raise SystemExit(f"Missing required file: {path}")
    original = PdfReader(str(ORIGINAL))
    v2 = PdfReader(io.BytesIO(render_addendum(ADDENDUM_V2.read_text(encoding="utf-8"))))
    v3 = PdfReader(io.BytesIO(render_addendum(
        ADDENDUM_V3.read_text(encoding="utf-8"), "Multi-Mode AI Assistant - Specification v3 Addendum")))
    writer = PdfWriter()
    for part in (original, v2, v3):
        writer.append_pages_from_reader(part)
    writer.add_metadata({"/Title": "Multi-Mode AI Assistant Complete Specification v3",
                         "/Subject": "Original specification, v2 addendum and v3 flow, safety, memory and file addendum"})
    with OUTPUT.open("wb") as handle:
        writer.write(handle)
    print(f"Wrote {OUTPUT.name}: {len(original.pages)} original + {len(v2.pages)} v2 + {len(v3.pages)} v3 pages")


if __name__ == "__main__":
    main()
