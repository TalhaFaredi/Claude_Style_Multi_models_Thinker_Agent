"""Output Builder (spec stage 5): turns the checked answer into text or a file, after a final safety check.

    formats.py      Markdown -> PDF (reportlab) and static web page
    artifacts.py    store, fetch and delete the generated files
    final_check.py  C21: secrets removed, empty answers replaced
"""
from app.output.artifacts import build_artifact, delete_chat_artifacts, document_content, get_artifact
from app.output.final_check import final_check
from app.output.formats import fit_pdf, pdf_pages, requested_pages

__all__ = ["build_artifact", "delete_chat_artifacts", "document_content", "get_artifact", "final_check", "fit_pdf", "pdf_pages", "requested_pages"]
