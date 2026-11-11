# Frontend specification audit

Reviewed against the complete 15-page PDF extracted to `spec-audit/specification.txt`, especially Part 3 (pages 12–15). Product files were not changed. This is an audit, not a claim that all untested behaviors work.

## Executed validation

| Check | Result | Qualification |
|---|---|---|
| Exact frontend source: Vitest | 24/24 passed | Existing pure-domain/reducer tests; not a complete integration test suite. |
| Exact frontend source: TypeScript | Passed | `tsc --noEmit`, exit 0. |
| Exact frontend source: production webpack build | Blocked/failed | Native SWC is blocked by Windows Application Control, but WASM fallback works. Fatal issue was network EACCES while `next/font/google` fetched Inter and Source Serif 4. No successful exact-source production build established. |
| Isolated demo copy, production webpack build | Passed | Only Google font imports/initializers and generated font className were removed from the audit copy. No user's `.env.local` or existing `.next` changed. This is **not** an exact-source build pass. |
| Existing browser smoke on that isolated demo copy | 49/49 passed; zero console/page errors | All three modes, Auto, plan approval, Stop, cost dialog, files/cache demo, context alarms/demo compaction, import demo, keyboard focus and phone width. Uses scripted model/file/memory results, not real backend/providers. |
| Additional browser assertions on that copy | 7/10 passed; 3 failed | F4 Files-only model filtering failed; F12 reset failed twice. F5/F6/F8/F13 paths passed. F8 used a synthetic persisted $0.05 ask threshold because existing demo files all cost under the minimum $0.10 UI choice. |

Commands used the installed Node runtime at `C:\Users\iWSL-WS\AppData\Local\Programs\cursor\resources\app\resources\helpers\node.exe` (v24.22.1), because Node/npm are absent from this shell's PATH. No live model API calls were made.

Artifacts: `frontend-extra-checks.mjs`, `frontend-extra-results.json`, `frontend-extra-output.txt`, `frontend-build-results.txt`, `frontend-smoke-results.txt`, and `frontend-shots/` (14 screenshots). Temporary demo build/server are cleaned up after execution.

## Findings

### High: “New chat with summary” discards the current working state and displays an invented success message

- Requirement: Part 3 §7 alarm/context action “New chat with summary”; Part 2 §7 says the chat must not forget silently.
- Evidence: `frontend/src/store/chatStore.ts:337` calls `newChat()` and then installs a hardcoded system message: “12 facts and the file cards came with it.” `newChat()` at line 330 clears messages and attached files and picks a new chat ID. No summary is generated, no facts/cards are copied, and no backend handoff request is made. The new summary message exists only in client memory.
- The action is offered to live users by `components/layout/Banners.tsx:28` and `components/dialogs/ContextDialog.tsx:33`; it is not guarded as demo-only.
- Consequence: user believes continuity was preserved while the new chat has none of the promised carried context. Original chat remains stored, but the advertised new-chat behavior is false.

### Medium: F4 allows a tool-incapable model when File reader is the only enabled tool

- Requirement: Part 3 F4 greys out models without tools whenever tools are on.
- Evidence: `frontend/src/components/dialogs/ModelPickerDialog.tsx:57` computes `needs.tools` using `simple.tools.web || simple.tools.code`; it omits `simple.tools.files`.
- Browser reproduction: Simple → Setup → turn Web search and Code off, leave Files on → model picker → Llama 3.3 is enabled despite its `tools:false` metadata. Additional assertion expected disabled=true, got false. When selected, SimpleSetup disables all tool controls and the user's file-tool preference is effectively ignored.
- Existing unit test of `modelDisabledReason` passes because it supplies `needs.tools=true` directly and never tests this component's incorrect calculation.

### Medium: “Reset everything to safe defaults” resets only four values

- Requirement: Part 3 F12 / §8 offers Reset to safe defaults.
- Evidence: `frontend/src/store/settingsStore.ts:37` defines SAFE_DEFAULTS as only reader, askLimit and autoCompact; `resetSafe` at line 75 applies only these. `components/settings/DataTab.tsx:34` additionally resets question budget. Other settings and all model/team choices remain untouched.
- Browser reproduction: disable “Remember facts across chats”; enable Temporary chat; click “Reset everything to safe defaults.” Temporary chat remains true and Remember facts remains false. Both differ from the initial defaults and both extra assertions fail.
- The UI's broad label makes the resulting saved configuration misleading. Chart/image settings, monthly budget and working-window choice also remain changed by inspection.

### Medium: offline sends do not retain the message as a draft

- Requirement: Part 3 §10 explicitly requires an offline state with the message kept as a draft.
- Evidence: `frontend/src/store/chatStore.ts:184` clears the draft before the request. `frontend/src/services/runner/sseRunner.ts:36–38` emits only an error on network failure; the reducer's error case does not restore the draft. `frontend/src/domain/messages.ts:20` has no offline status. Initial startup failures replace the chat UI with an error screen (`AppShell.tsx:57`).
- The prompt remains visible as a user message and the error offers Retry, but the requested offline/draft behavior is absent. Confirmed by source inspection; no live-backend network-drop browser run was performed.

### Medium: the plan approval card cannot display each step's done-test

- Requirement: Part 3 §4 Plan card must show task, mode, done-test, status; Part 1 §6 includes done-test in every plan step.
- Evidence: `backend/app/modes/planner/plan.py:96` strips `done_test` when constructing the plan event. `frontend/src/domain/events.ts:18` defines no done-test field. `frontend/src/components/chat/PlanCard.tsx:31` renders task/mode/note/status only.
- Consequence: the user approves execution without seeing the criteria that the step checker will enforce. The backend may still check its internal done-test; this finding concerns the required reviewable UI.

### Medium: approval/edit network errors disappear while the UI advances optimistically

- Requirement: Part 3 §6/§10 requires clear waiting/error states and retryable failure behavior.
- Evidence: `frontend/src/services/runner/sseRunner.ts:42–47` ignores both non-2xx responses and fetch rejection for approve/edit/stop. `chatStore.ts:281` immediately removes approval waiting state; edit also immediately hides the approval UI.
- Consequence: if an approval request fails, the server can remain waiting while the UI removes the Approve button and appears to be working. User must Stop/restart or wait for timeout rather than retry the failed approval. Source-inspection finding, not an induced live-network failure.

### Additional explicit specification gaps

- **Maximum answer length:** Part 1 §4 says the user can set it. SimpleConfig and SimpleSetup expose only model/thinking/style/tools; no answer-length control or request property exists (`domain/types.ts:39`, `components/dialogs/setup/SimpleSetup.tsx:31`).
- **Composer card:** Part 3 §4 specifies a green card with composer model, status and merge explanation. `components/chat/TeamProgress.tsx` has only progress/agent cards, and `AnswerBlock.tsx:38` has no composer-card component. Backend status text may mention composing, but the specified card is absent.
- **Locked Planner limits presentation:** Part 3 §5 says approval, 2 retries, 2 re-plans and 20 steps should be shown as locked. SetupDialog's final lock text shows approval, max 10 tool calls and retries; it omits max re-plans and max steps (`components/dialogs/SetupDialog.tsx:123`).
- **40px target minimum:** Part 3 §2 requires 40px minimum targets. `.btn.small` is 32px high, `.seg-btn` 34px, and stepper buttons 34×34 (`styles/base.css:18`, `:27`, `:63`).
- **Password-protected export:** required by Part 3 §7 and Part 2 §8; explicitly unavailable in live capability metadata (`backend/app/api/meta.py:29`), so ExportDialog shows an unavailable note instead (`components/dialogs/ExportDialog.tsx:76`). Clear communication, but still incomplete.
- **Independent default:** Part 1 §7 / Part 3 §5 require “On their own” default. `domain/defaults.ts:17` sets `style:'together'`. Backend defaults correctly use independent and replace invalid demo model defaults on a fresh live boot, so this discrepancy chiefly affects the demo/default frontend configuration.
- **Model speed column:** Part 3 §4 requires speed per model row; ModelInfo/picker render price/capabilities/company/provider but have no speed field/rendering.
- **Build portability:** the README says unavailable fonts fall back to system fonts offline, but the attempted exact-source build was fatal at font fetch. Self-host fonts or provide a true build-time fallback to remove this environment dependency.

## F1–F13 requirement matrix

“Pass on exercised path” means observed in the isolated demo browser (or specifically identified unit test); it does not establish real backend/provider correctness.

| ID | Status | Evidence / limitation |
|---|---|---|
| F1 | Pass on exercised path | Empty Send disabled; unit and smoke. |
| F2 | Implementation/unit pass; click coverage partial | Mixed team with one member is blocked by unit test. Normal picker prevents dropping below two. No persisted-invalid-team click test was run. |
| F3 | Pass on exercised path | Browser max-five/min-two model/agent checks and toast; rounds bounds unit-tested. |
| F4 | **Fail** | Files-only tools do not filter incompatible models; extra browser assertion. |
| F5 | Pass on exercised path | Chart file attached → nonvision picker row disabled; extra browser assertion. |
| F6 | Pass on exercised path | Select Mistral → Off selected, High disabled; extra browser assertions. |
| F7 | Partial | Ordinary Send cost dialog passes smoke. `send(override)` explicitly skips it (`chatStore.ts:267`), Think deeper uses that route, and Retry goes straight to beginRun (`:297`). Server enforcement is separate. |
| F8 | Pass on synthetic exercised path | Amber ask-limit warning and free Text only choice work. Demo fixture with synthetic persisted $0.05 threshold; not a live paid-reader test. |
| F9 | Pass on exercised path | Mode locked during run and unlocked after Done/Stop; smoke. |
| F10 | Pass on exercised path | No demo plan step runs before Approve; smoke. Real backend gate reviewed by root. |
| F11 | Pass on exercised path, failure feedback flaw | Keep/Delete confirmation passes smoke. `MemoryTab.tsx:44` announces “Deleted everywhere” before async API success; a failure can leave the fact while briefly claiming deletion. |
| F12 | **Fail** | Reset leaves Temporary chat and longMemory values unchanged; two failed browser assertions. |
| F13 | Pass on exercised path | Strong/weak mixed-model warning observed; extra browser assertion. |

## Part 3 section coverage

| Section | Assessment |
|---|---|
| 1 Design idea | Substantial implementation; fake summary handoff and swallowed failures undermine the promised transparency. |
| 2 Visual style | Tokens/colors/fonts largely match; 40px minimum violated by several controls. |
| 3 Layout | Desktop/phone screen, dialogs, composer and sidebar present; smoke finds no phone horizontal overflow. |
| 4 Components | Most present; composer card, per-step done-test and model speed absent. |
| 5 Modes/controls | All mode UIs present; independent frontend default, Planner limit display and answer-length gaps above. |
| 6 Message flow | Mode flows/demo Stop pass; async control error behavior and F7 resend bypass need work. |
| 7 Files/memory/context | Much is wired; new-chat-with-summary is fake; password lock absent. Demo tests do not establish real readers or compaction accuracy. |
| 8 Settings | Controls and auto-save calls present; reset incomplete. Failed saves only show toast, leaving optimistic UI state. |
| 9 Guardrails | Matrix above: F4/F12 fail; F7 partial. |
| 10 States/access/sizes | Focus/Escape and phone smoke pass; offline draft state absent, touch target sizes below spec. No exhaustive screen-reader/contrast audit. |
| 11 Structure/tests | Component/store/domain separation and SSE exist. 24 unit / 49 demo click checks pass, yet they miss confirmed component/configuration failures. Full live multi-provider operation unverified here. |
