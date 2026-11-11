# Pipeline, Thinker and Planner audit

Reviewed against PDF pages 1–6 and the cross-cutting requirements on pages 7–15 on November 9, 2026 (Asia/Seoul). These are findings about the current repository, not promises about provider behavior.

Evidence: `reproduce_orchestration.py` reproduces nine defects offline, using an in-memory database and mocked calls. Application source was not changed. The existing backend suite separately passed 52/52 tests.

Severity: P1 = approval, spending, data preservation or quality-control failure; P2 = material functional/spec gap; P3 = smaller interface/completeness gap. This is a project audit priority, not a security CVSS rating.

## O1 — P1: Editing can bypass Planner approval

PDF p4 §6, C15/C18, frontend F10: no step may execute without an approved plan; edits must regenerate it and show it again.

- `backend/app/modes/planner/run.py:48`: after five edits, a sixth `edit` falls through to `return steps, meta` at line 53. The caller then sets the steps to waiting and runs them. The user has never pressed Approve.
- `backend/app/modes/planner/run.py:68`: at a substantial re-plan approval, only `cancel` is handled. An `edit` response is treated as approval and its note is discarded.
- The API approval queue also accepts messages without checking that the run is currently awaiting approval (`backend/app/api/runs.py:34`); queued approvals can outlive the plan for which they were sent. No plan version is carried by the approval.

Reproduced both Edit cases. Fix the state transitions so only an explicit approval for the current plan version releases the gate; keep Edit within the approval loop even when the edit limit is exhausted.

## O2 — P1: Final Planner content is never checked

PDF p2 Figure 1 and p4 Figure 4 require final assembly → Checker → Output Builder.

`backend/app/modes/planner/assemble.py:31` generates new content, then streams it directly (line 37) or writes a downloadable artifact (line 39). It never calls `checker.check`. `backend/app/pipeline/engine.py:189` only runs `output.final_check` on the returned text, which is the short file-ready message for artifacts. `backend/app/output/final_check.py:9` redacts secret-like strings and substitutes an empty answer; it does not validate the assembled document against the goal.

Reproduced a new, unchecked final answer being returned with zero Checker calls. The artifact's “Checked” UI label cannot establish that its actual contents passed the required final check.

## O3 — P1: Stop loses completed Planner content

C20 requires saving progress and returning partial results and remaining steps.

Completed content lives in `Step.result` (`backend/app/modes/planner/steps.py:74`). `plan_view` at `backend/app/modes/planner/plan.py:94` serializes task, mode, status and note, omitting result. On cancellation, `backend/app/pipeline/engine.py:172` catches it outside `run_planner`, saves `rc.view['text']`, then returns. It does not recover the local Step objects. Budget exceptions at `planner/run.py:101` and the outer timeout have the same structural problem before assembly.

Reproduced: finish step 1 containing `FIRST_COMPLETED_RESULT_987`, start step 2, press Stop. The saved answer is empty; the plan marks step 1 done, but its actual content is absent from the saved answer/view. Persist step outputs as they finish and produce partial output from the persisted steps on all exits.

## O4 — P1: Checker failures silently pass

`backend/app/pipeline/checker.py:33` catches every ordinary exception and returns `CheckResult(True)` at line 34. Invalid/non-object responses also pass. That includes unavailable providers and `BudgetExceeded`, which inherits from `Exception`. No warning says the quality check did not run.

Reproduced an unavailable Checker silently passing an unverified answer. At minimum report that checking was unavailable; do not mark it as a successful check or swallow the budget stop.

The default also streams drafts before checking (`backend/app/core/config.py:101`). This is an explicit repository deviation from PDF Figure 1's “nothing reaches the user without passing the Checker.” Setting `STREAM_BEFORE_CHECK=0` addresses early streaming for Simple/Thinker, but does not add the missing final Planner check.

## O5 — P2: The 20-step cap does not cover re-plans

`backend/app/modes/planner/plan.py:43` allows 20 new steps regardless of `offset`. `planner/run.py:63` prepends all completed steps. Reproduced normalization of 20 new steps with offset 19, yielding a combined plan of 39 steps. C20 and the fixed 20-step limit on PDF p6 are not enforced across re-plans. Limit remaining steps by the already completed count and define a run-wide execution limit.

## O6 — P2: Failed Simple steps do not escalate to the team

C16: a failed Simple step retries with the team unless the user chose Simple-only; T1 also requires an offer to use the team in that case.

`backend/app/modes/planner/steps.py:63` reevaluates the unchanged `Step.kind` and `runIn` on every attempt. An easy Auto step stays Simple after failure. Reproduced two Simple attempts and zero team calls for a failed-then-passing Auto step. The frontend also lacks the required T1 “Use the team” action.

## O7 — P2: Later debate failures bypass the fewer-than-two fallback

`backend/app/modes/thinker/run.py:69` checks the active count after round 1. The return value from later `run_round` calls at line 81 is ignored, and line 98 goes to the composer even when only one agent survives. Reproduced one survivor after round 2 reaching the composer with zero Simple fallback calls. Re-check the live answer count before judging, advancing rounds and composing, as required by C13/T6.

## O8 — P2: Reusing a run ID replaces another chat's archived answer

`RunRequest.id` is supplied by the caller. `backend/app/api/runs.py:23` only rejects IDs for currently unfinished runs. `execute` uses that ID as the assistant message ID. `backend/app/memory/archive.py:52` uses `INSERT OR REPLACE` with a global message primary key, rather than a scoped insert or collision rejection.

Reproduced storing two assistant messages with the same run ID in different chats: the original archived message disappears. Ordinary UI IDs are random, so accidental collision is unlikely, but the API does not preserve the Archive invariant for reused IDs. Generate message IDs on the server or reject global reuse without replacing stored content.

## O9 — P2: Clarification is limited to short first messages in Auto

`backend/app/pipeline/router.py:46` returns immediately for a manually selected mode, before any clarity assessment. In Auto it accepts a clarification only for messages of six words or fewer with no existing history or files (`router.py:65`). C2 and the Input Gateway figure do not restrict clarification this way. This is a deliberate narrowed implementation, not full compliance.

## O10 — P2: File grounding is not enforced across all modes

Simple provides `excerpts` to the Checker (`backend/app/modes/simple/run.py:68`). Thinker composer calls `checker.check` without excerpts (`backend/app/modes/thinker/composer.py:52`); Planner step checks also omit excerpts (`backend/app/modes/planner/steps.py:71`). `checker.py:37` ignores the model's unsupported-claim list whenever excerpts is empty. The C32 new-search loop therefore only exists for Simple. Final Planner assembly has no Checker at all (O2).

## O11 — P2: Some Planner/team requirements are only approximated

- C17: after two re-plans, the Planner warns and stops (`planner/run.py:108`); it does not ask the user how to proceed.
- C18: reapproval depends on step-count or estimated-cost growth (`planner/run.py:65`), with no detection of a materially changed goal.
- T10: the composer-first retry correctly skips the agents and judge, but `run_thinker` still gathers web facts and rebuilds context before the reuse branch (`thinker/run.py:52`–67). Web gathering adds a tool call, and search-mode file context can call the query-rewriting model (`backend/app/files/search.py:96`), so it is not guaranteed to be the stipulated single model call.
- T4: the one-time gather routine only gathers web search. File context is built, but there is no general one-time execution of all the tools requested by a team step.
- Thinker constructs one shared context using its first agent's model (`thinker/run.py:58`) and reuses it for other agents and the composer, with no per-model fit check. This matters when mixed models have different context windows or image support (C3/C38).
- Simple configuration and API have no maximum answer length control (`backend/app/api/schemas.py:14`); hardcoded output limits replace the spec's user setting.
- T11: `backend/app/modes/planner/estimate.py:18` prices every mixed agent using `team.model` and the composer using `simple.model`, ignoring the selected mixed model IDs and custom composer. Tool-kind steps are skipped entirely although `_run_alone` makes a model call for them. The generic pre-Send CostDialog offers a cheaper setup; the generated-plan approval path does not compare the new estimate with budget and offer plan-specific reductions.

## Part 1 requirement matrix

“Implemented path” means the code path exists and relevant offline evidence was found. It does not certify real model quality, paid providers, or all boundary conditions. “Partial” means a path exists but a material required branch is missing or defective. Related reports provide cost/tool/output details.

| ID | Assessment | Evidence / limitation |
|---|---|---|
| C1 | Partial | Regex deny-list before model calls; known matching harmful input refused in existing tests; no comprehensive safety gate. |
| C2 | Partial | O9: Auto-only, short first-message clarification. |
| C3 | Failing edge cases | Context can overflow or silently exclude recent raw turns; see memory report. |
| C4 | Implemented path | Explicit mode respected by router; existing pipeline tests. |
| C5 | Implemented path; quality unverified | Small-model Auto routing plus regex fallback; no fixed known-answer routing benchmark gate. |
| C6 | Implemented path | Uncertain Auto routes to Simple; UI offers Think deeper. |
| C7 | Partial | UI estimate gate/server warning exist; estimates and concurrent budget enforcement are incomplete (LLM report). |
| C8 | Partial | Retry/fallback paths exist; 401/402 abort chain; streaming retry/truncation defects (LLM report). |
| C9 | Partial | Simple can switch to a tool-capable model; Planner `_run_alone` instead omits tool schemas without switching or explaining. The adapter does filter fallback models for advertised tool support. |
| C10 | Partial | Ten executions per tool-loop invocation; disabled tools can still execute; retries reset count (LLM report). |
| C11 | Missing workflow | Risky tools excluded/unavailable; no allow/deny permission flow or runnable Docker sandbox. |
| C12 | Implemented path | Debate bounded to 1–3 rounds; agreement judge can stop early; tests cover early stop. |
| C13 | Partial | First-round fallback tested; later-round failure defect O7. |
| C14 | Partial | Automatic composer chosen using budget heuristic; no per-run actual context/capability guarantee. |
| C15 | Failing edge cases | O1: sixth Edit and substantial-replan Edit can resume without approval. |
| C16 | Partial | Two retries and feedback exist; Simple-to-team escalation missing (O6). |
| C17 | Partial | Two re-plans bounded; user consultation after exhaustion missing. |
| C18 | Partial | Cost/count change prompt exists; Edit ignored; changed goal not checked. |
| C19 | Partial | Exhausted checks add warning; last draft sent without comparing earlier draft quality; unavailable Checker passes silently. |
| C20 | Failing edge cases | Stop, budget and timeout handlers exist; lose Planner step content, exceed run-wide step cap; cost races. |
| C21 | Partial | Secret redaction/empty-text replacement and artifact plain-text fallback; no required full safety/format validation and repair pass. |
| T1 | Partial | Simple-only routing exists; no Use the team offer after failure. |
| T2 | Implemented path | Auto marks hard steps for team; pure routing tests pass. |
| T3 | Implemented path | Tool-kind steps run alone; still invoke an LLM rather than direct output-tool execution. |
| T4 | Partial | Web gather and shared file context exist; generic gather-once and model compatibility gaps O11. |
| T5 | Partial | Tier-mismatch warning exists; no clear automatic comparable-model suggestion. |
| T6 | Partial | Same-model copies drop and mixed-model fallback is attempted; later-round count defect O7. |
| T7 | Implemented path | Agreement judge stops remaining debate; existing test confirms. |
| T8 | Partial | Prompt asks for change reason; round-1 answers retained; missing change explanation is accepted. |
| T9 | Implemented path | Composer sees role labels rather than model identities; existing test checks. |
| T10 | Partial | Composer-first then team retry exists; additional gather/context work, not guaranteed one call. |
| T11 | Partial | Approval shows a team-inclusive estimate, but mixed/custom-composer prices are ignored and tool-step calls omitted. Generic cheaper setup exists before Send; generated-plan approval has no plan-specific budget/reduction gate. |

## Required acceptance gates remain unproven

PDF p6 §9 requires a fixed known-answer set, the four team cases compared with Simple on quality/cost, long tasks inside all limits, and routing accuracy. PDF p11 requires 20 PDFs with correct table/chart page citations and ≥95% recall of 50 planted facts after compaction AND import. Existing scripted tests exercise mechanics; they do not establish these gates. No honest claim that the app works “perfectly” follows from 52 passing offline tests.
