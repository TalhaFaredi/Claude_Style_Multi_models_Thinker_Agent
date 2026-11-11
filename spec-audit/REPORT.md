# Specification audit — November 9, 2026

> Historical pre-fix findings. The application has since been updated; see [IMPLEMENTATION.md](IMPLEMENTATION.md) for current changes, measured verification results and remaining environment/quality limits. The reproduction probes below intentionally describe the old behavior.

**The application is not fully compliant with the specification and cannot be described as working perfectly.** The main architecture is implemented and many normal flows pass. However, the audit reproduced failures in approval, budget enforcement, context preservation, export/import, tool controls and Planner output checking.

The audit read all 15 pages of `Multi-Mode_AI_Assistant_Complete_Spec (1).pdf` and mapped the numbered requirements C1–C44, T1–T11 and F1–F13 to implementation and available verification. The extracted source is [specification.txt](specification.txt). A successful UI event or mocked test is not treated as evidence of real answer quality or OCR accuracy.

Application code and the user's real chat database were left unchanged. Added files are audit notes, isolated reproductions, test output and browser evidence under `spec-audit/`. Provider behavior was mocked for targeted backend reproductions; no paid provider calls were made. Mock dollar amounts below illustrate defects in control flow, not real charges incurred during this audit.

## Verification results

| Check | Result | What this establishes |
|---|---|---|
| Existing backend offline suite | **52 passed** | Existing scripted backend tests pass using the installed virtual environment. |
| Existing frontend unit suite | **24 passed** | Existing pure-domain/reducer checks pass. |
| Frontend TypeScript check | **Passed** | Current frontend source type-checks. |
| Exact-source production webpack build | **Failed in this environment** | Next's font loader could not download Inter and Source Serif 4 due to blocked network access. No exact-source production build pass is claimed. |
| Demo browser smoke | **49 passed, zero console/page errors** | An isolated frontend copy built after removing only Google font-loader imports. Exercises scripted demo flows; does not validate live providers or the exact production artifact. |
| Additional browser assertions | **7 passed, 3 failed** | Files-only capability filtering fails; two reset assertions fail. Chart filtering, thinking restrictions, over-limit file choice and mixed-strength warning pass the exercised demo cases. |
| Orchestration reproductions | **9 defects reproduced** | Approval bypass, final-check bypass, stopped-step content loss, fail-open Checker, re-plan cap, escalation, later-round fallback and ID reuse. |
| LLM/cost/tool reproductions | **7 defects reproduced** | Budget races, reasoning allowance, hidden housekeeping costs, disabled tool execution, retry-stream contamination, truncated-stream accounting and provider fallback. |
| Memory/file probes | **Defects reproduced; details saved** | Lossy compaction, oversized context, paid “free” read, fact-history loss, reader interference, retained detached files, incomplete original-file restoration and missed vector charts. |

Backend command: `backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`, run in `backend/`. Frontend commands and runtime details are in the frontend report. The exact-source font-fetch build failure is an environmental verification limit, separate from the functional defects below.

## Fix first

| Priority | Finding | Evidence and spec requirement |
|---|---|---|
| P1 | **Question budgets are not hard limits.** Parallel calls reserve no money; reasoning allowance is omitted; housekeeping uses a separate budget and late charges disappear from the displayed/saved total. | [LLM report L1–L3](llm-tools-findings.md), C7/C20. Mock parallel example: $0.10 limit → $0.20 spent. |
| P1 | **Planner can execute without approval.** Sixth Edit exits the approval gate; Edit on a major re-plan is treated as approval. | [Orchestration O1](orchestration-findings.md), C15/C18/F10; `backend/app/modes/planner/run.py:48` and `:68`. |
| P1 | **Final Planner documents bypass the Checker.** Newly assembled text/files are delivered directly. A broken Checker also silently passes answers. | [Orchestration O2/O4](orchestration-findings.md), five-stage flow/C19/C21; `backend/app/modes/planner/assemble.py:31`, `backend/app/pipeline/checker.py:33`. |
| P1 | **Compaction can say success while omitting critical facts.** Only 60 missing details are reattached before old turns are replaced in context. | [Memory finding 1](memory-files-findings.md), C37. Mock summary of 80 amounts lost 20 from summary/ledger; originals remain archived. |
| P1 | **Prompts need not fit their context window.** There is no final fit enforcement and compaction may refuse the only recent messages. | [Memory finding 2](memory-files-findings.md), C3/C37/C38. Probe built 26,466 tokens for 3,400 usable tokens, about 778% of capacity. |
| P1 | **“Text only (free)” dispatches paid model work.** Zero-cost approval covers only a partial estimate; card writing and embeddings can still run. Embedding calls bypass the Cost Meter and monthly reading budget. | [Memory findings 3–4](memory-files-findings.md), C24/C28 and import reindex cost approval. |
| P1 | **Stop can lose completed Planner results.** Step status persists but completed content exists only in local Step objects until assembly. | [Orchestration O3](orchestration-findings.md), C20. Reproduced stopping during step 2 after step 1 completed. |
| P1 | **Disabled tools can execute.** A returned tool call is checked against the global registry, not the run's offered/enabled tool list. | [LLM L4](llm-tools-findings.md), tool controls. Empty advertised tools still executed a mocked web search. |
| P1/P2 | **Export/import changes memory meaning.** Replaced facts become current again, original dates disappear, used cross-chat facts are omitted, and chart images are discarded. | [Memory finding 5 and portability gaps](memory-files-findings.md), C39 and Part 2 §8. |
| P2 | **“New chat with summary” does not transfer context.** It creates a new chat and adds a hardcoded success message about transferred facts/cards. | [Frontend report](frontend-findings.md), Part 3 §7. |
| P2 | **File state can change across chats; deleted data can remain.** A second chat's newest reader replaces the first chat's active reading; detached files survive deletion of their only chat. | [Memory findings 7–8](memory-files-findings.md), C22/C42. |
| P2 | **Other Planner/team safeguards are incomplete.** Re-plans can exceed 20 total steps, failed easy Auto steps stay Simple, later debate failures skip Simple fallback, and plan prices ignore selected mixed agents/composer. | [Orchestration O5–O7/O11](orchestration-findings.md), C13/C16/C20/T10/T11. |

The P1/P2 grouping indicates repair order for this local application; it is not a formal security risk score. Inspect the detailed reports for exact triggers and qualifications.

## Remaining specification gaps

- Code sandbox execution and risky-tool permission UI are missing; risky execution is safely disabled.
- PNG output, PPTX reading, local/OCR-API readers, PDF layout parsing, vector-chart reading and query/chunk reranking are missing or incomplete.
- Stream retries can show abandoned partial text, incomplete SSE responses can be accepted with zero usage, and credential failure skips a healthy alternate provider.
- Unsupported-file claim checking is not consistently applied in Thinker/Planner; Simple retry checks use stale file excerpts.
- Offline sends do not restore the user's draft, reset does not reset all settings, and live plan rows omit the done-test required for approval.
- Password-protected exports, per-chat selected-reader stability, full attachment restoration, optional cache settings and complete durable tool traces remain incomplete.
- Clarification is narrowed to short first messages in Auto; maximum answer length is not exposed as specified.

Some substitutions—SQLite instead of suggested PostgreSQL/Redis, plain async state machines instead of LangGraph, and direct HTTP instead of vendor SDKs—are design choices. The PDF marks those stack choices as suggestions; the audit does not count a different library as a functional defect on its own.

## Complete requirement review

| Scope | Report |
|---|---|
| C1–C21 and T1–T11; pipeline, Simple, Thinker, Planner, approval and stop | [orchestration-findings.md](orchestration-findings.md) |
| C22–C44; files, memory, compaction, export/import and deletion | [memory-files-findings.md](memory-files-findings.md) |
| LLM adapter, registry, budgets, providers, tools, skills, outputs and logging | [llm-tools-findings.md](llm-tools-findings.md) |
| Part 3 and F1–F13; frontend controls, state, accessibility and browser results | [frontend-findings.md](frontend-findings.md) |

“Implemented” in these matrices means the inspected path exists and has supporting source/test evidence. It does not mean every model output or external dependency was proven correct. No overall compliance percentage is reported: the requirements vary in weight, and some mandatory quality gates are untested.

## Acceptance gates still required

The PDF requires more than scripted UI success:

1. A fixed set of questions with known correct answers, including all four team cases compared with Simple on quality and cost.
2. Long Planner tasks completing within budget, time, retry, re-plan and total-step limits under failure and concurrency.
3. Auto routing accuracy against expected modes.
4. Twenty PDF fixtures with correct table/chart answers and page citations.
5. At least 95% recall of 50 planted facts after compaction **and import**.
6. Context meter estimates compared with actual provider token counts, plus successful real provider retry/fallback and file-reading checks.

These gates were not established by the existing tests or this offline audit. Live OpenRouter/NVIDIA availability, current model access/capabilities, OCR accuracy and real end-to-end inference remain unverified. Repository comments and old live-test claims were not treated as fresh evidence.

## Reproduce and inspect the evidence

From repository root, using the existing backend virtual environment:

```powershell
.\backend\.venv\Scripts\python.exe spec-audit\reproduce_orchestration.py
.\backend\.venv\Scripts\python.exe spec-audit\llm_offline_repros.py
.\backend\.venv\Scripts\python.exe spec-audit\probe_memory_files.py
```

These are audit probes of current behavior, not regression tests asserting the desired behavior. Backend data is isolated from `backend/data`; provider calls are mocked. Evidence files: [orchestration-results.txt](orchestration-results.txt), [llm-results.jsonl](llm-results.jsonl), [memory-files-probe-results.json](memory-files-probe-results.json), [frontend-extra-results.json](frontend-extra-results.json). Browser evidence is described in the frontend report.

Repair spending/approval/data-preservation defects first, then complete the missing required flows, then run the PDF's acceptance gates with bounded live tests. Passing the present unit suites alone is insufficient for sign-off.
