# Specification implementation and verification

Updated November 10, 2026 (Asia/Seoul). This document supersedes the historical November 9 audit as the implementation status. The PDF remains the design source. No provider keys or existing user chats were changed during verification; tests use isolated data.

## Verified results

| Check | Result |
|---|---|
| Backend tests | **133 passed** (108 before the afternoon live audit; 25 regressions added for the defects listed below) |
| Frontend unit/transport tests | **36 passed**; TypeScript passes |
| Exact-source production webpack build | **Passes**, with locally bundled Inter/Source Serif 4; no font-download workaround needed |
| Browser specification gate | **25/25 passed**, covering F1–F13, control errors, offline recovery, permission denial, continued chat and team recovery, using a deterministic HTTP/SSE fixture |
| Live three-mode smoke | Simple, Thinker and Planner each produced the required answer/output within approved budgets |
| Fixed live comparison/routing set | **33/33 correct** across Simple, all four team cases and three Auto cases; all runs within cost/time limits |
| Live memory gate | **50/50 facts recalled after compaction and 50/50 after export/import** |
| Generated PDF retrieval gate | **40/40 table/chart retrieval assertions across 20 PDFs**; real parsing/rendering/indexing, mocked chart descriptions |
| Live PDF reading/answer gate | **20/20 passed**, with real vision descriptions, correct table/chart facts and correct file/page citations; $0.001633 total |
| Local OCR | A real bundled RapidOCR model reads a generated image without provider calls |

Live comparison results: [live-acceptance-2026-11-10.json](live-acceptance-2026-11-10.json). Memory results: [live-memory-2026-11-10.json](live-memory-2026-11-10.json). Final direct-builder Planner result: [live-planner-final-2026-11-10.json](live-planner-final-2026-11-10.json), correct in 14.6 seconds at $0.000127. Browser details: [browser-results-2026-11-10.json](browser-results-2026-11-10.json).

Live PDF results: [live-files-2026-11-10.json](live-files-2026-11-10.json). Each of the 20 generated two-page PDFs contains a ruled capacity table and a vector bar chart. Gemma 3 12B reads the rendered chart, and the configured answer model answers from the saved reading. All 40 requested facts and their file/page references were correct. This is a controlled fixture gate, not a benchmark of diverse real-world scans, handwriting or chart styles. No descriptions or answers were mocked in this live run.

The saved live reports account for **$0.01720542** across the comparison, memory, file and Planner/smoke runs, including the earlier timed-out Planner attempt. This remains within the $0.03 verification allowance. Tests used isolated databases and the existing user data was not reset. Both the browser-fixture build and the normal production build completed successfully; the browser servers were shut down after testing.

The numeric evaluator accepts Markdown/LaTeX representations of the same exact answer. Two correct fraction answers were initially false negatives; their saved outputs were re-scored offline. Reports identify evaluation version 2; answers, calls and costs were not altered.

On this six-question comparison set, Simple and every team case scored 100%. Teams cost more, so **no team case demonstrated an accuracy gain or qualified as a better cost/quality default on this set**. The report's `teamBeatsSimple` gate is false and `defaultEligible` is false for those more expensive cases. Team use remains an explicit supported mode; independent style remains the specified UI default. A harder, independently fixed benchmark is still needed to demonstrate the roadmap's phase-2 quality advantage. No such advantage is claimed here.

## Live audit, November 10 (afternoon)

A second, independent pass re-read the PDF and drove the real frontend and backend with real cheap models on isolated data ($0.043 in total). The earlier results above were obtained on servers started the previous day; the running servers were restarted on the current code first. Defects found and fixed, each with a regression test in `backend/tests/test_audit_fixes.py` or `test_spec_orchestration.py`:

| Defect (measured) | Fix |
|---|---|
| Router asked a clarifying question on clear questions (6/20; worse, 40/48, after a longer prompt) and Thinker never ran | Router returns `understood`; a question is accepted only when `understood` is false. Measured after: 0/48 false questions, 18/21 vague messages still asked |
| Planner team steps always fell back to Simple: qwen3.7-flash at thinking "low" spent the whole allowance on reasoning and returned empty text | Agents answer without hidden reasoning; the client re-asks once without reasoning when reasoning consumed the answer |
| "1-page PDF" delivered as 2 pages, unchecked: the file joined every dependency (raw research above the report), an 8B model guessed page counts, and retries rebuilt identical text | File = final draft only; the output step is checked by measuring the file; overflow shrinks type slightly, then shortens to a word limit; Markdown rules/loose lists render compactly. Live: 1-page, Checked, 37 s, $0.0023 |
| Correct file answers replaced by "could not find support" (llama-3.1-8b checker failed the correct answer 3/4 on the real context) | Separate `CHECKER_MODEL`, default qwen3.7-flash (21/21 vs 18/21) |
| Every memory-based answer failed its first check (12/12) because the Checker could not see remembered facts; a third ended as "I do not have access" | Checker receives the memory, summaries and recent turns. Live: 12/12 recalled, 12/12 first-check passes |
| At an 8k working window every turn could be refused: rules + skills exceeded a hard 5% cap that compaction cannot reduce | Optional skills give way; only files and summaries keep hard caps |
| One common word picked a wrong skill (5/22 prompts; "my favorite color is teal" got design advice) | Skills have strong `triggers` and weak `hints`; a skill needs one trigger or two hints |
| Checker returned unreadable JSON and the final file was labelled unverified | One re-ask; "true"/"false" strings accepted |

Live browser gate after the fixes: **49/49 passed, no console errors** (Auto/Simple/Thinker/Stop, Planner edit/approve/PDF, file pricing/reading/citation/reuse, cross-chat memory, auto-compaction recall, password export/import, delete). Backend: **133 passed**. Frontend: 36 unit tests and typecheck pass; production build succeeds.

## Main changes

- Atomic in-flight spending reservations cover concurrent calls, schemas, reasoning and cache charges. Compaction, retrieval and post-reply writes share the approved question cap. Unknown provider charges are conservatively recorded and identified.
- Stream completion and usage are checked. Retries reset abandoned drafts or buffer until a successful attempt. Rejected credentials skip to an available alternate provider. Mandatory-reasoning models get a disclosed, budgeted minimum allowance.
- Tool calls enforce per-answer allow-lists, argument validation, counters across retries and explicit risky-action permissions. Tool traces persist. Docker execution has network/filesystem/user/resource/time/output isolation and container cleanup.
- Plan approvals are versioned; missing/stale versions and duplicate approvals fail. Edits and replacement plans wait for approval. Failed Simple steps escalate only as permitted; Simple-only plans offer Use the team.
- Step contents and artifacts are checkpointed. Stop/timeout/budget exits preserve completed work. Stop acknowledgement includes settled costs, including cancellation during post-answer writes.
- Output steps build actual files directly. Final contents are checked before delivery, including extracted document content from proposed file-write envelopes. PDF page counts use real rendering; explicit page breaks, tables, Unicode PDF and safe PNG output are supported.
- Free text reading and Document Cards stay local. Paid file reads disclose their maximum, support selected pages, enforce monthly budgets and keep reader selections per chat. PDF tables/vector charts, PPTX/Office pictures, local OCR, explicit OCR API routing, vision and reranking are implemented.
- Compaction preserves all detected critical details with their original relationships. Context enforces full fit/part budgets; no silent raw-turn trimming. Ledger updates, historical facts, archive recall and genuine continued chats are implemented.
- Encrypted export/import retains dates, replacements, used facts, originals, images and vectors. Changed-model meaning indexing has an explicit approval endpoint/UI, preserves completed batches, and never repeats OCR.
- Frontend controls now recover from offline/control failures, reset fully, disclose one-question/manual-summary caps, show done-tests/composer/permissions/checked state, and use local fonts and accessible target sizes.

## C1–C21

“Implemented/tested” refers to the supported path and relevant deterministic/live evidence; it is not a guarantee that arbitrary model outputs will be correct.

| ID | Current implementation |
|---|---|
| C1 | Known unsafe requests refuse before paid calls; small-model input assessment adds broader safety/clarity checking. Refusals do not trigger paid memory writes. |
| C2 | One clarifying question applies to explicit modes and Auto, without the former six-word/first-message restriction. |
| C3 | Context fit is enforced; checked compaction/file chunking are used, or the user receives a clear fit failure. |
| C4 | Explicit mode respected. |
| C5 | Auto routes facts, comparisons and multi-step/file tasks; live routing set passes 3/3. |
| C6 | Uncertain Auto uses Simple with Think deeper. |
| C7 | Send/Retry/Think deeper share the estimate gate; generated plans offer cheaper setups. Approved caps are explicit. |
| C8 | Two retries, available/capable fallback, provider-wide credential skipping, stream reset and usage accounting. |
| C9 | Tool-capable selection or an explicit limitation; fallback capabilities filtered. |
| C10 | Ten executions per answer/step across retries; disabled tools cannot execute by hallucinated name. |
| C11 | Pending permission event and Allow/Deny API/UI. Docker runner implemented; actual host prerequisite remains below. |
| C12 | Independent/debate rounds, bounded to 1–3 with agreement stop. |
| C13 | Fewer-than-two fallback checked after later rounds too; partial agent results persist. |
| C14 | User composer or highest available configured strength tier within allowance; no hidden budget floor. |
| C15 | Edits regenerate and show the plan again; sixth Edit cannot approve implicitly. |
| C16 | Feedback retries bounded to two; eligible failed Simple steps use the team, Simple-only requires user choice. |
| C17 | Two re-plans maximum, then a clear request to change goal/model in a new question. |
| C18 | Every replacement plan is reapproved, including goal/cost changes. |
| C19 | Best scored draft plus warning after exhausted checks; unavailable/invalid Checker is never silently passed. |
| C20 | Whole-pipeline deadlines, budget reservations, total plan-step cap, Stop and persisted partial results/accounting. |
| C21 | Final safety/control/secret checks; document envelope normalization; format validation, one repair and plain-text fallback. |

## C22–C44

| ID | Current implementation |
|---|---|
| C22 | Fingerprint/reader/version cache reuse costs $0; selected reader is stable per chat. |
| C23 | Direct DOCX/PPTX/XLSX/CSV reading; embedded Office pictures use OCR paths. |
| C24 | Text extraction/local cards do not dispatch paid model or embedding work on Text only. |
| C25 | Configured Auto/local/OCR-API/vision routes; local OCR tested with real bundled weights. |
| C26 | PDF layout tables and direct Office tables; chunk headers retained without cutting rows. |
| C27 | Full PDF-page rendering, vector-chart detection, bounded visual descriptions and kept images. The live generated-PDF visual/citation gate passes 20/20. |
| C28 | Approved maxima, page/reader alternatives, monthly budget and 80% alarm; embedding calls also metered. |
| C29 | Reader retry once then next available route; paid fallback cannot exceed its approval. Weak pages identified. |
| C30 | Full text when within the file budget; cards and text precede the newest message. |
| C31 | Rewrite, keyword/meaning search, fusion, query/chunk reranking and table/image expansion. |
| C32 | Unsupported claims trigger new evidence/retry; Checker receives the refreshed evidence in all applicable modes. |
| C33 | Chart images for compatible models, descriptions otherwise; saved images survive import. |
| C34 | Normal meter below 70%. |
| C35 | Notice at 70%. |
| C36 | Alarm/actions at 85%; Later threshold handling tested. |
| C37 | Checked compaction and final context-fit enforcement; originals retained. Live recall gate passes. |
| C38 | Smaller/team context windows checked; a prompt that cannot fit is not silently truncated. |
| C39 | Dated fact replacement history retained in live storage and encrypted round-trip. |
| C40 | Date-filtered original-message recall and historical fact retrieval. |
| C41 | Temporary chats / memory off prevent long-term reads and writes. |
| C42 | Chat/file/fact/index/artifact deletion paths; last detached file is purged instead of orphaned. |
| C43 | Version/checksum/schema checks name bad parts; malformed imports validated before mutation. |
| C44 | Imported instructions remain data; imported system roles cannot become system prompts. |

## Team rules

| ID | Current implementation |
|---|---|
| T1 | Simple-only steps stay Simple unless user explicitly selects Use the team. |
| T2 | Auto marks hard steps for team; eligible failed Simple steps escalate. |
| T3 | Output-only steps execute the file builder directly without extra agents or a pretend-write model call. |
| T4 | Facts/file context gathered for sharing; tool scopes/citations shared. Composer-only retry reuses gathered evidence. |
| T5 | Mixed-strength warning and similar-strength suggestion. |
| T6 | Failed copies dropped / mixed agents use nonduplicate replacements; fewer-than-two fallback enforced. |
| T7 | Judge skips remaining rounds on agreement. |
| T8 | Revision explanation requested/enforced; round-1 answers retained, including on reused composer retries. |
| T9 | Composer uses role labels, not model identity labels. |
| T10 | Composer-only first retry then full-team retry; cached evidence/debate state retained. |
| T11 | Mixed-agent/composer prices and output work included; over-budget approval blocked with cheaper-plan choices. |

## Frontend guardrails

| ID | Current implementation/evidence |
|---|---|
| F1 | Empty Send disabled. |
| F2 | Persisted invalid teams blocked with explanation. |
| F3 | Agent/round steppers and limit toast. |
| F4 | File-reader-only tool selection also filters incompatible models. |
| F5 | Chart attachments filter nonvision choices. |
| F6 | Unsupported thinking set to Off with explanation. |
| F7 | Pre-spend gate for Send, Retry and Think deeper; explicit Allow-once cap. |
| F8 | Amber reading threshold and Text only / cheaper reader / selected pages. |
| F9 | Mode locked during active work. |
| F10 | Versioned approval before execution; done-tests visible. |
| F11 | Keep/Delete confirmation; failed deletion retains the fact. |
| F12 | Full defaults reset; fixed safety limits cannot be changed. |
| F13 | Strength-mix warning and comparable-model suggestion. |

The 25 browser assertions cover these guardrails plus acknowledged control errors, offline draft recovery, permission denial, persisted summary handover and explicit team recovery. The final frontend source builds unchanged, with its normal local fonts.

## Remaining environment and quality limits

1. **Docker is not installed on this host.** The runner, permissions and isolation are implemented/tested with process mocks; actual container execution requires Docker's Linux engine and the configured Python image. The UI accurately disables it until available. The safe calculator remains usable.
2. **Teams did not beat Simple on the measured set.** All were correct; more calls did not improve that score. The phase-2 advantage gate remains unproven, and no expensive case is certified as an improved default by this benchmark.
3. **NVIDIA access/rates depend on the configured account.** Unknown prices and unavailable providers are greyed out. No live cross-provider NVIDIA inference is claimed.
4. Model-generated answers and summaries can still be wrong on new tasks. Checks, limits and warnings are implemented; the measured results apply to the saved fixed test sets, not every possible question or file. No exhaustive screen-reader/contrast certification is claimed.

## Reproduce

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe tests/live_spec_acceptance.py   # manifest only; no network
.\.venv\Scripts\python.exe tests/live_memory_acceptance.py # no network
.\.venv\Scripts\python.exe tests/live_file_acceptance.py   # no network
# Real inference only when explicitly selected, always capped:
.\.venv\Scripts\python.exe tests/live_spec_acceptance.py --live --cap 0.02 --per-run 0.003 --timeout 120
.\.venv\Scripts\python.exe tests/live_memory_acceptance.py --live --cap 0.005
.\.venv\Scripts\python.exe tests/live_file_acceptance.py --live --cap 0.01

cd ../frontend
npm test
npm run typecheck
npm run build:webpack
```

Older local pre-fix probe files assert historical defects and are not current passing regression tests. Current regressions live in `backend/tests/` and `frontend/tests/`.

Provider integration references used to verify implementation: [OpenRouter embeddings request](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings), [embedding-model metadata/pricing](https://openrouter.ai/docs/api/api-reference/embeddings/list-embeddings-models), [PDF parser routing](https://openrouter.ai/blog/extract-tables-from-pdf-llm/). Exact live charges come from saved provider usage, not the documentation examples.
