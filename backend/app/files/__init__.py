"""Attachment pipeline (spec Part 2 sections 3 to 5). A file is read once and never paid for twice.

    common.py     constants, FileError, PageInfo, fingerprint()
    readers.py    free text extraction: PDF, Word, Excel, text and code (C23, C24)
    analysis.py   free page check and the price of each reader (C25 to C28)
    vision.py     vision reader for scans and charts
    card.py       Document Card
    chunking.py   800-token chunks; tables never cut mid-row
    search.py     keyword + meaning index, search, full-text vs search mode (C30 to C33)
    store.py      upload, Parse Cache, read, detach, purge (C22, C42)
"""
from app.files.analysis import kinds_summary, reader_availability, reading_plan
from app.files.card import cards_text
from app.files.chunking import chunk_pages
from app.files.common import READER_IDS, FileError, fingerprint
from app.files.search import FileContext, chat_readings, file_context, index_chunks, reindex_estimate, reindex_file, search_chunks, total_file_tokens
from app.files.store import (chat_fingerprints, detach, file_status, forget_chat, ingest, is_linked, link, purge_file, read_file,
                             store_original, reading_estimate)

__all__ = ["kinds_summary", "reader_availability", "reading_plan", "cards_text", "chunk_pages", "READER_IDS", "FileError", "fingerprint",
           "FileContext", "chat_readings", "file_context", "index_chunks", "search_chunks", "total_file_tokens",
           "chat_fingerprints", "detach", "file_status", "forget_chat", "ingest", "is_linked", "link", "purge_file", "read_file", "store_original"]
