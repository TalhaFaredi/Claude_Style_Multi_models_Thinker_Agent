"""Shared constants and small types for the attachment pipeline."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

READER_IDS = ("auto", "text", "local", "api", "vision")
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".tsx", ".html", ".xml", ".yaml", ".yml", ".log", ".sql", ".java", ".c", ".cpp", ".go", ".rs"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
PAGE_CHARS = 3000             # pages for formats that have none (txt, docx)
VISION_PAGE_TOKENS = 1600     # one page image (spec Part 2 section 4)
CHART_OUT_TOKENS, SCAN_OUT_TOKENS = 300, 700
OCR_API_PER_PAGE = 0.002      # Mistral OCR: $2 per 1,000 pages


class FileError(Exception):
    def __init__(self, message: str, status: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.status, self.extra = status, extra or {}


@dataclass
class PageInfo:
    page: int
    kind: str            # "text" | "scan" | "chart"
    chars: int = 0
    table: bool = False
    images: int = 0

    def to_dict(self) -> dict:
        return {"page": self.page, "kind": self.kind, "chars": self.chars, "table": self.table, "images": self.images}


def fingerprint(data: bytes) -> str:
    """SHA-256 of the bytes: the same file always gets the same ID, so it is never paid for twice."""
    return hashlib.sha256(data).hexdigest()
