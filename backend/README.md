# Multi-Mode Assistant backend

FastAPI implements the PDF's five-stage pipeline: Input Gateway, Mode Router, Simple/Thinker/Planner, Checker and Output Builder. Shared services provide model metadata, tools, archive/memory, attachment readers, costs and usage logs.

The current design update is the [v2 specification PDF](../Multi-Mode_AI_Assistant_Complete_Spec_v2.pdf) and its [addendum](../spec-audit/SPEC-ADDENDUM.md). The prior verification matrix is in [spec-audit/IMPLEMENTATION.md](../spec-audit/IMPLEMENTATION.md); its measurements predate the v2 model/cost display changes.

## Start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep provider keys in the root `.env`, or process environment variables. Names accepted are `OPENROUTER_API_KEY` / `open_router_api` and `NVIDIA_API_KEY` / `nvidian_key`. API docs are at `/docs`; health is `/health`. Accounts are on by default (`AUTH_REQUIRED=1`): every `/api` route needs a signed-in session and every query is scoped to the user. `AUTH_REQUIRED=0` gives the old open single-user mode for local use only. Production setup is in `../DEPLOYMENT.md`; the interactive docs at `/docs` are switched off when `APP_ENV=production`.

OpenRouter's live registry supplies prices and capabilities. NVIDIA metadata is entered explicitly. Unknown prices are unavailable rather than assumed free: configure `NVIDIA_INPUT_USD_PER_MILLION` and `NVIDIA_OUTPUT_USD_PER_MILLION` to the rates for your account. Provider health checks use read-only endpoints and do not run test inference.

`GET /api/models` returns the full loaded catalog. Each model includes tentative small (1k-5k), medium (5k-50k) and high (50k-500k) token price ranges under a 70% input/30% output single-call assumption. Unknown prices and context-incompatible bands are marked unavailable. These bands are distinct from the question-specific budget estimate and actual post-call usage.

`GET /api/prompts` returns shipped Markdown templates with role labels and literal placeholders, including the shared system rules and every Thinker role. It never renders or returns a user's prompt, documents, memory or tool output. During a run, `model_thinking` events carry only provider-exposed reasoning notes, and `call_usage` events carry per-call model/stage/agent labels, tokens, USD and an estimated flag. A provider or model may return no reasoning notes.

Useful configuration:

| Setting | Purpose |
|---|---|
| `DATA_DIR` | SQLite, uploaded originals, page images and generated files; defaults to `backend/data` |
| `UTILITY_MODEL`, `WRITER_MODEL`, `VISION_MODEL` | Small routing/judge model, memory/summary writer and visual reader |
| `CHECKER_MODEL` | Answer Checker; defaults to `qwen/qwen3.7-flash` (21/21 correct verdicts in the Nov 10 audit vs 18/21 for llama-3.1-8b) |
| `EMBED_MODEL` | Meaning-search model; defaults to `openai/text-embedding-3-small` |
| `EMBED_INPUT_USD_PER_MILLION` | Required explicit input rate when selecting a different embedding model |
| `WINDOW_CAP_TOKENS` | Initial working-window cap, also configurable in Settings |
| `RUN_TIMEOUT_S`, `PLANNER_TIMEOUT_S`, `CALL_TIMEOUT_S` | Overall Simple/Thinker, Planner and individual provider timeouts |
| `STREAM_BEFORE_CHECK` | Defaults to `1`: the draft streams while it is written and the Checker can still replace it. `0` holds the draft until it is checked |
| `APP_TOKEN` | Empty by default (open, only safe on `127.0.0.1`). When set, every `/api` route needs `Authorization: Bearer <token>`; the web app asks for it once. Set it before the server is reachable from another machine |
| `CHECK_ANSWERS` | Defaults on; disabling it marks answers unverified rather than silently passing them |
| `CODE_SANDBOX_IMAGE` | Installed Docker image for code execution; defaults to `python:3.12-alpine` |
| `CORS_ORIGINS` | Allowed frontend origins |

User Settings include OCR reader, paid-reading threshold/monthly budget, chart descriptions/page images, memory/temporary chat, auto-compaction, working-window cap and five-minute/one-hour prompt caching. Changes validate and save atomically.

## Run guarantees and limits

- Each dispatched provider call reserves its maximum estimated cost atomically. Concurrent agents, retries, reasoning allowances, retrieval and post-reply memory share the approved question cap. Unknown remote charges are conservatively recorded and labelled.
- A run has two retries per call/step, two re-plans, at most 20 combined plan steps, ten tool calls per answer/step across retries, a deadline and Stop. Actual charges and partial results are persisted even when Stop arrives during memory work.
- Planner approval applies to one plan version. Missing/stale approvals are rejected; edits regenerate the plan and wait for approval. Replacement plans ask again. A Simple-only failed step offers an explicit team retry.
- Tool execution verifies the run's allow-list and argument schema. Risky tools require explicit permission. The model cannot enable a disabled tool by returning its name.
- Checker failures are visible. Final Planner content is checked, with bounded corrective attempts and a warning if no draft passes; a failed draft is not labelled Checked. Requested numeric PDF page counts are compared with actual rendering.
- Approved output-only steps execute the file builder directly. PDF, Markdown, PNG, safe static HTML, plain text and code downloads use sanitized names. A failed format is repaired once, then returned as plain text with a warning.

Model correctness is measured separately. A check or team agreement is not proof that every model answer is correct.

## Memory and files

The Archive stores original messages, with IDs, timestamps, tokens and sources. Session ledger changes are incremental; long-term fact changes retain dated replacement history. Temporary chats do not read or write long-term memory.

Context is built in spec order with answer space reserved. No unsummarized turn is silently cut away to fit a smaller model. Compaction checks critical details and keeps their original factual statements. If the protected history or a context part cannot fit safely, the run asks the user to summarize/change the window/start a continued chat. New chat with summary creates a real persisted handover with ledger, facts and file links.

Attachments use SHA-256 and a reader/version Parse Cache. Reader choice belongs to each chat. Normal extraction and Document Cards are local; paid reads require a displayed, approved cap and respect the monthly reading budget. The UI can select a reader or a subset of pages, and shows the monthly alarm at 80%.

- PDFium renders full pages; pdfplumber handles PDF tables/layout and vector-chart detection.
- DOCX, PPTX, XLSX and CSV text/cells are extracted directly; embedded Office pictures have OCR paths.
- RapidOCR uses bundled local ONNX weights without provider requests. Mistral OCR explicitly selects OpenRouter's parser. Vision describes chart pages; failed readers retry once and move through available readers without exceeding approval.
- Chunks retain file/section/page and table headers. Retrieval supports full text or BM25/meaning search, fusion, reranking, neighboring/full-table expansion and chart images.
- Images, cached readings, vectors, original files when selected, ledger, summaries and dated fact history survive ZIP export/import. Optional AES password protection is implemented.
- An embedding-model change keeps keyword search ready. Paid rebuilding has a separate estimate/approval route and preserves successfully completed batches for retry; it never repeats OCR.
- Deleting a chat or the last file link removes associated data, indexes and generated files. Idle cleanup repairs dangling indexes without deleting original words.

## Code sandbox

Code runs only in Docker's Linux engine, with no network, a read-only filesystem, an unprivileged user, dropped capabilities, CPU/memory/process/output limits and a ten-second timeout. Containers are removed on completion, timeout or cancellation.

The server checks both the daemon and installed image. If Docker is absent, code execution is unavailable with an explanation; the calculator remains available. With Docker installed and running, prepare the default image using `docker pull python:3.12-alpine`, then restart the backend. No host-code fallback is used.

## API additions

| Endpoint | Behavior |
|---|---|
| `POST /api/runs` | SSE run; `simple.maxTokens`, separate `planModel`, explicit `budgetUsd` |
| `POST /api/runs/{id}/approve` | Requires `{planVersion}` |
| `POST /api/runs/{id}/edit` | Requires `{note, planVersion}` |
| `POST /api/runs/{id}/permission` | `{id, allow}` resolves one pending tool permission |
| `POST /api/runs/{id}/use-team` | `{step}` uses a zero-based failed step index |
| `POST /api/runs/{id}/stop` | Waits for cancellation accounting; returns final `usd` and `calls` |
| `POST /api/chats/{id}/fork` | `{model, maxCost}` creates a real continued chat |
| `POST /api/chats/{id}/compact` | Same cap fields; streams checked compaction progress |
| `POST /api/files/{fp}/read-estimate` | Reader/page-specific cost and cache reuse |
| `POST /api/files/{fp}/read` | `{chatId, reader, textOnly, maxCost, pages?}` |
| `GET /api/files/{fp}/reindex-estimate?chatId=...` | Cost of missing/current-model vectors |
| `POST /api/files/{fp}/reindex` | `{chatId, maxCost}` explicitly approves rebuilding |
| `GET /api/chats/{id}/export` | `includeFiles` query; optional `X-Export-Password` header |
| `POST /api/import` | ZIP multipart file, optional `password` field; checksums validated first |
| `GET /api/usage` | Model/stage totals, estimated usage, reading spend and 80% alarm |
| `GET /api/prompts` | Versioned static system/agent/step templates for review |

See `/docs` for all chat, settings, memory, model, artifact and rating routes.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
# No network by default:
.\.venv\Scripts\python.exe tests/live_spec_acceptance.py
.\.venv\Scripts\python.exe tests/live_memory_acceptance.py
.\.venv\Scripts\python.exe tests/live_file_acceptance.py
# Optional real calls, each with a hard aggregate budget:
.\.venv\Scripts\python.exe tests/live_spec_acceptance.py --live --smoke --cap 0.03 --per-run 0.01
.\.venv\Scripts\python.exe tests/live_memory_acceptance.py --live --cap 0.005
.\.venv\Scripts\python.exe tests/live_file_acceptance.py --live --cap 0.01
```

Offline tests use an in-memory database and `data_test/`, never the real archive. Tests include concurrency/stream failures, permissions, approval/version changes, Stop, rendered output, encrypted portability, 20 generated PDF retrieval fixtures and 50-fact context preservation. The offline PDF test mocks visual descriptions. The separate opt-in live PDF runner uses actual vision and answer models, with isolated data and an aggregate budget; its saved run passes all 20 generated table/chart fixtures with correct page citations. Live reports record actual answers, costs and gate results; these controlled fixtures do not certify arbitrary real-world files.

Source is organized by responsibility: `api/`, `pipeline/`, `modes/`, `llm/`, `core/`, `files/`, `memory/`, `output/`, [prompts/](app/prompts/README.md), [skills/](app/skills/README.md), [tools/](app/tools/README.md).
