# Multi-Mode Assistant frontend

One Next.js/React chat screen implements the specification's Auto, Simple, Thinker and Planner modes. State, costs, context, file reading and approval progress come from the FastAPI backend through typed HTTP/SSE contracts.

## Run

Use Node 20+ and install dependencies with `npm install`. Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local` for the real backend; leave it unset for the scripted demo. Provider keys belong only in the root server `.env`.

Routes: `/` landing page, `/signup` `/login` `/forgot` `/reset`, `/app` the assistant (needs an account in live mode), `/account`, `/admin`, `/terms`, `/privacy`. Site name, contact and legal details come from `NEXT_PUBLIC_SITE_*` / `NEXT_PUBLIC_CONTACT_EMAIL` / `NEXT_PUBLIC_OPERATOR_NAME` / `NEXT_PUBLIC_LEGAL_REVIEWED` (fixed at build time; see `src/domain/site.ts`). The browser tests open `/app`.

```powershell
npm run dev:webpack
# Production:
npm run build:webpack
npm start
```

Inter and Source Serif 4 WOFF2 files are bundled in `src/app/fonts` and loaded with `next/font/local`, so builds do not download fonts. The webpack scripts support this machine's WASM compiler fallback when native Next binaries are blocked by Windows Application Control.

## Implemented flows

- Setup exposes model/tool/thinking choices and maximum answer length. Planner has separate plan-writer and step-model controls. Independent thinking is the default; agents/rounds and fixed safety limits are visible.
- Model rows show price/capabilities/company/provider and measured speed when available. File-reader-only tools also filter incompatible models. Nonthinking/nonvision choices explain their restrictions.
- Send, Retry and Think deeper share budget preparation. Allow once displays and transmits an explicit one-question cap without multiplying the configured budget silently.
- Planner shows task, kind, mode, done-test and status. Approve/Edit send the displayed plan version. Failed controls preserve retryable UI; over-budget plans offer a cheaper setup; a failed Simple-only step can explicitly use the team.
- Composer progress has a dedicated card. Risky tools require a displayed Allow/Deny choice. Generated files show Checked only when their actual content passed checks.
- Lost connections keep the message as a draft. Stop waits for server acknowledgement/accounting and preserves progress. Drafts and archived messages remain recoverable.
- Context warnings expose checked summarizing and a real persisted new-chat handover. Manual summary/fork actions disclose their cost cap before dispatch.
- File uploads are checked free, then show reader/page selection, expected cost versus approved maximum, reuse and the monthly reading alarm. Text only stays free. Document Cards retain page/table/chart references.
- Password-protected export/import is wired. Changed embedding models offer an explicit, priced meaning-index rebuild while keyword search stays ready.
- Memory deletion reports success after server acknowledgement. Reset restores all configuration defaults. Settings save immediately; failed writes keep visible feedback.
- Answers render safe Markdown/tables, without raw model HTML execution. Controls have labels, dialogs handle focus/Escape, touch targets are at least 40px, and phone rows wrap.

## Verify

```powershell
npm test
npm run typecheck
npm run build:webpack
```

The deterministic browser gate covers F1–F13 plus network failure, failed approval/deletion, permission denial, continued chat and team recovery. It starts and stops its own fixture/backend substitute and Next server; it never calls model providers:

```powershell
$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8487'
$env:NEXT_BUILD_DIR='.next-spec-live'
npm run build:webpack
npm run test:spec
```

The older demo smoke can run separately:

```powershell
$env:MMA_DEMO='1'
$env:NEXT_BUILD_DIR='.next-spec-demo'
npm run build:webpack
npm start -- --port 3137
# Another terminal: E2E_URL=http://localhost:3137 npm run test:e2e
```

Chrome or Edge is required; `E2E_CHANNEL=msedge|chrome` selects it. Node/npm may not be on this host's shell PATH; the installed Cursor helper Node binary also runs the local Next/Vitest/TypeScript entry points.

`test:live` is a separate older provider-backed integration script; use only against isolated test data with a bounded budget. The backend's new `live_spec_acceptance.py` and `live_memory_acceptance.py` measure current provider correctness separately from UI fixtures.

## Structure

| Directory | Responsibility |
|---|---|
| `src/domain` | Types, mode/limit rules, reducer, context/cost formatting |
| `src/store` | Chat, chats list, settings, models and dialog state |
| `src/services` | API, acknowledged SSE controls, batching and demo runner |
| `src/components` | Layout, chat blocks, setup/dialogs, settings and reusable controls |
| `src/styles` | Specification tokens and responsive styles |
| `tests`, `e2e` | Unit/transport checks and browser gates |

For current measured results and remaining environment/quality limits, see [spec-audit/IMPLEMENTATION.md](../spec-audit/IMPLEMENTATION.md). A deterministic browser pass does not certify real model accuracy or every screen-reader/contrast combination.
