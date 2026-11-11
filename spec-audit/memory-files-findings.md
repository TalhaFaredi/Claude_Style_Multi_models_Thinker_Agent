# Memory, attachments, portability audit

Reviewed the full extracted specification, especially PDF pages 7–11 (Part 2), and the corresponding backend implementation. Product code was not modified. Reproductions use an in-memory SQLite database, an isolated `spec-audit/probe-data` directory, and a fake LLM. No real provider calls or user database writes were made. A synthetic image is passed only to the mocked vision reader for the reader-selection probe.

Run the reproducible probes from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe spec-audit\probe_memory_files.py
```

Results: [memory-files-probe-results.json](memory-files-probe-results.json). Mock dollar amounts demonstrate accounting behavior and are not live provider prices.

## High priority findings

1. **Compaction reports success while dropping checked critical details.** PDF p.10 requires numbers, names and dates to be kept before a summary replaces originals (C37). `backend/app/memory/compaction.py:145` computes missing details but `:147` only reattaches the first 60; `:151` still removes all selected messages from the working window and `:156` returns `ok=True`. Probe: place 80 distinct amounts in an old message and return a lossy summary and no ledger edits. It reports 80 details preserved, yet `$1061`–`$1080` (20 amounts) are missing from the resulting summary/ledger. Originals remain in the archive, but ordinary next turns no longer include these facts. Source is also truncated at 24,000 characters for ledger extraction (`:102`) and 32,000 for summaries (`:110`), and fallback preserves only eight 240-character prefixes (`:144`). The “nothing silently lost” claim and the required 95% recall gate cannot be accepted from these tests.

2. **The Context Builder does not enforce the usable window.** PDF pp.9–11 requires fixed part budgets, compaction before overflow, and handling smaller models (C3/C37/C38). `backend/app/memory/context.py:110` loads all unsummarized history, `:129` appends every message, and `:148` returns even if the total exceeds usable capacity. There is no final fit check, bounded recent-turn budget, or guaranteed summary budget. Probe: five 20,000-character messages and a 4,000-token window produce a prompt estimated at 26,466 tokens against 3,400 usable (778%). Compaction refuses because nothing is older than the last ten messages (`compaction.py:125`). The engine warns or attempts a single compaction and continues (see `backend/app/pipeline/engine.py:114`); it does not require the rebuilt prompt to fit. Actual provider failure was not exercised.

3. **“Text only (free)” can spend despite a zero-dollar approval.** PDF pp.7–8 requires free text extraction, cost visibility and paid-step approval (C24/C28). `backend/app/files/store.py:97` compares approval only with the OCR/vision estimate; `:104` then grants an independent budget of at least $0.05; `:136` always calls `make_card`. `backend/app/files/card.py:30` uses a paid writer model. Probe: text-only read with `max_cost=0`, estimated $0, calls `file:card` and returns mock actual cost $0.0001. `store.py:144` additionally indexes embeddings, which bypass cost accounting (next item). The UI explicitly labels this path free (`frontend/src/components/dialogs/LiveFileDialog.tsx:80`).

4. **Embedding calls bypass budgets, approval and the usage ledger, including during import.** `backend/app/files/search.py:39` calls the embeddings HTTP endpoint directly, reads only vectors (`:43`) and never records returned usage or invokes `CostMeter`. `index_chunks` is used after reading (`store.py:144`), during retrieval (`search.py:126`), and during import (`memory/portability.py:203`). `monthBudget` and `askLimit` are stored/displayed but not enforced in the reading backend; `chartDescriptions` is stored and never consulted in page routing. Import has no stored embedding-model identity and cannot show/ask for changed-model reindex cost, despite Part 2 §8 step 3. This is established by source inspection, not a live billing experiment.

5. **Export/import loses memory dates and revives replaced facts.** PDF pp.9–11 requires dated facts and replacement history (C39) and all facts used in a chat in the export (Part 2 §8). `backend/app/memory/portability.py:60` omits fact IDs/replacement links and includes only facts created by this chat. `:174` calls `add_fact` without restoring timestamps or replacements. Probe: historical “Budget is $5” replaced by “Budget is $20” returns from import as two current facts, both dated at import time. A fact created in chat A that is actually inserted into chat B's prompt is absent from B's export (`facts.json` is empty). Importing also adds duplicates to the global memory pool while original facts remain.

6. **Chart and table reading is incomplete, especially for ordinary vector PDF charts.** C26 requires a layout parser preserving tables; C27 requires chart descriptions and kept page images. `backend/app/files/analysis.py:28`–`:33` classifies only by character count and embedded raster-image count; it does not inspect vector diagrams or garbled text. `backend/app/files/vision.py:24` extracts the largest embedded image instead of rasterizing the entire page. A generated PDF containing a titled three-bar vector chart is classified as ordinary text with zero images and no page image; its bars never reach vision. A text-heavy page containing an embedded chart is also classified as text when it has >=400 characters. Table handling consists of whitespace/pipe heuristics (`analysis.py:14`) and raw `pypdf.extract_text()` (`readers.py:25`), with no layout parser. This cannot substantiate the required 20-PDF table/chart accuracy gate.

7. **Another chat's reading choice silently changes an existing chat's attached file.** C22 keys readings by file fingerprint and reader. The cache stores both readers, but `file_chats` stores no selected reader and `backend/app/files/search.py:69` always chooses the newest reading for the fingerprint globally. Probe: chat A reads a scan with Auto, chat B reads the same scan with Text only. Chat A then switches from Auto to the text reading and has zero file tokens, losing its OCR text until a different reading becomes newest. This can change a previously working answer after activity in an unrelated chat.

8. **Deleting a chat does not purge files detached earlier.** C42 requires removal from every store/index/cache. `backend/app/files/store.py:148` detaches by deleting the link only; `:173` discovers files to purge only from links still present at chat deletion. Probe: ingest/read a file, detach it, delete its only chat. The original file row, saved reading and indexed chunks remain. No orphan-cleanup path was found. Files still linked at deletion are correctly purged when no other chat uses them.

## Other material gaps

- **PowerPoint is unsupported; Office embedded pictures are not OCRed (C23).** `backend/app/files/readers.py:75` supports PDF, DOCX, XLSX/XLSM, text/code/CSV and raster images, but `.pptx` returns HTTP 415. DOCX only counts inline images (`:61`) and vision extraction returns `None` for non-PDF/non-image formats (`vision.py:20`); XLSX read-only cell extraction ignores pictures. OCR API and local readers explicitly return unavailable/501 (`analysis.py:50`, `store.py:88`). Vision-only fallback is useful but does not implement the specified reader set or one-retry/next-reader chain (C29).
- **There is no reranker (C31).** `backend/app/files/search.py:138` truncates reciprocal-rank fusion to the top eight directly. The requested query-plus-chunk reranking of up to 50 candidates is absent. Only immediate table neighbors are expanded, so arbitrarily long tables need not arrive whole.
- **C32 retry checking uses stale excerpts.** `backend/app/modes/simple/run.py:57` initializes `excerpts` once; retry searches at `:72` insert new evidence only into the answer prompt at `:74`; the checker at `:61` still receives the initial evidence. A corrected answer based on newly found passages can continue failing because the checker never sees those passages. Checker excerpts/draft are further limited to 6,000 characters (`pipeline/checker.py:28`).
- **Exports discard chart page images.** `backend/app/memory/portability.py:73` sets every saved image to `None`, and no image parts are written. Import repeats that removal (`:198`). Chart descriptions may survive, but direct visual follow-up (C33) cannot be restored from the saved reading without reconstructing/re-reading an image.
- **Unread original files are not restored.** Export with original files includes their bytes (`portability.py:76`), but import only iterates `readings/` entries (`:178`). Probe: an uploaded unread text file is present in the ZIP and the import reports zero restored files.
- **Password-locked ZIP export is not implemented.** `backend/app/memory/portability.py:49` rejects passwords with 501. UI discloses this limitation. Part 2 §8 / Part 3 §7 requests the feature.
- **The session ledger is not updated after every turn.** `write_turn_memory` writes long-term facts only; `ledger_apply` is called in compaction, import or directly in tests. PDF p.9 Figure 8 says the Memory Writer updates ledger and facts after every reply. Temporary chats can therefore lose useful ongoing ledger updates until compaction.
- **Historical fact retrieval is incomplete.** `add_fact` keeps replaced facts, but removes their FTS entry (`facts.py:20`); `relevant_facts` always excludes replacements (`:50`). `recall_originals` searches only the current chat's original messages (`recall.py:36`). Cross-chat historical memory questions cannot retrieve the old fact through the normal context path, although the history-list API can display it.

## Requirement matrix: C22–C44

“Implemented” means source and existing/offline behavior support that code path; it does not certify live model quality. Frontend visual behavior is audited separately.

| ID | Status | Evidence / qualification |
|---|---|---|
| C22 | Partial | Same fingerprint/reader/version cache returns $0, but active reader choice is global/latest and is not stable per chat. |
| C23 | Partial | DOCX/XLSX/CSV direct reading exists; PPTX and OCR of embedded Office pictures do not. |
| C24 | Partial | Ordinary text extraction is free; full text-only read still calls the paid card writer and embeddings. |
| C25 | Partial | Scans/photos can use vision; local and OCR-API settings are unavailable. |
| C26 | Partial | Direct DOCX/XLSX rows and table chunk headers exist; no PDF layout parser. |
| C27 | Fails for vector charts | 300-token vision description path exists for detected raster charts; vector/text-heavy charts are missed and full-page images are not rendered. |
| C28 | Incomplete | Client shows ask limit, backend compares optional approval with partial estimate; actual approved cap/month budget not enforced. |
| C29 | Partial | General model retries/fallback exist; configured-reader retry-once/next-reader chain is absent; failed pages marked weak. |
| C30 | Implemented with limits | Full text placed near beginning when it fits file allocation; allocations use usable window and omit some wrapper/image overhead from fit choice. |
| C31 | Partial | Rewrite + BM25 + embedding search + rank fusion exist; reranker missing; embeddings fail soft to keywords. |
| C32 | Partial | Up to two fresh searches and unsupported warning exist; retries are checked against stale excerpts. |
| C33 | Partial | Saved raster chart images can be attached for vision models; vector charts/imported images unavailable. |
| C34 | Backend implemented | `level_for` and meter support normal level. |
| C35 | Backend implemented | 70% threshold supported; UI audited separately. |
| C36 | Backend implemented | 85% threshold supported; 4 buttons/Later handling are frontend concerns. |
| C37 | Incomplete | Compaction triggers exist, but prompt can remain too large and critical-details cap can silently drop facts. |
| C38 | Incomplete | Window calculation supports smaller model, but no guaranteed rebuilt-prompt fit; engine checks requested Simple model even for other-mode execution. |
| C39 | Partial | New facts replace old with dates in live DB; export/import destroys dates/replacement links; historical context retrieval incomplete. |
| C40 | Implemented with limits | Archive search applies approximate date range and returns originals within current chat; context clips each returned message to 500 characters. |
| C41 | Implemented | Memory writer and reader guard temporary chat / longMemory off. |
| C42 | Partial | Linked chat files, messages, indexes, artifacts and selected memories deleted; previously detached file data survives. |
| C43 | Implemented for checksums/version | Unsupported version/checksum failures name the part; broader malformed JSON/schema errors are not uniformly wrapped or rolled back. |
| C44 | Implemented at prompt boundary | Import maps system roles to user; shared rules label documents/memory/summaries as DATA; actual model resistance to malicious content not live-tested. |

## Verification limits

No OCR/vision accuracy benchmark, live provider token-count comparison, 20-PDF citation benchmark, or 50-planted-facts 95% recall-after-compaction-and-import gate was executed here. Existing memory tests cover a small fixed group of facts, not the required benchmark. An `ok=True` summary or successful import response is insufficient evidence that all spec guarantees hold.
