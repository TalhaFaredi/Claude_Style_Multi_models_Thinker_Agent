# LLM, costs, tools, skills and output audit

Audited against the 15-page root PDF extracted to `specification.txt`. Product code was not edited. All reproductions used an in-memory database and mocked providers/tools. No provider requests, paid inference or real chat-data writes were made.

Run the independent reproductions from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe spec-audit\llm_offline_repros.py
```

## Confirmed defects

### L1 — High: concurrent calls can spend past the question budget (C7, C20)

`backend/app/core/costmeter.py:33` checks only money already charged. It does not reserve the cost of an in-flight request. `backend/app/llm/client.py:289` performs this check, awaits the provider, and only adds the cost at line 301. Multiple concurrent agents or Planner steps can each approve their call against the same remaining amount.

Reproduction: two concurrent mocked calls each costing $0.10 both pass a $0.10 meter and finish with **$0.20 spent**. A lock around each individual check/add does not make the entire request lifecycle atomic.

Required change: atomically reserve the full expected maximum before dispatch; release or reconcile the reservation on every success, error, retry and cancellation. Every concurrent caller must share that reservation ledger.

### L2 — High: the budget guard ignores extra reasoning tokens it actually requests (C20)

`backend/app/llm/client.py:290` prices `max_tokens`, but `_body` adds 1,024 / 2,048 / 4,096 tokens for low / medium / high at lines 121–124. These extra billable tokens are not included in the preflight amount. Tool schemas are also outside `estimate_messages(messages)`.

Reproduction with an intentionally simple $0 input / $1,000-per-million output mock: a 100-token call passes a **$0.10 budget**, then high thinking sends a **4,196-token** cap and is charged **$4.196**. Real model prices change the dollar amounts, but the same under-budgeting path exists.

Required change: construct the actual request first and reserve the cost of the total output cap, reasoning allowance, tool schemas and applicable input/cache charges.

### L3 — High: housekeeping can exceed the question budget and its cost is omitted from saved/displayed totals (C20; shared Cost Meter; Part 3 costs in sight)

`backend/app/pipeline/engine.py:30` allocates a separate $0.50 housekeeping meter. `house_ctx` at line 84 bypasses the user's question meter for compaction and memory. The displayed and saved total is calculated at line 194, before post-run compaction and the background Memory Writer scheduled at line 209. The late costs never update that message's stored cost or displayed total.

Reproduction: mocked answer costs $0.01; background memory costs $0.02. After the writer finishes, **displayed cost = $0.01**, **saved message cost = $0.01**, **actual combined meters = $0.03**. This also means a question that fits its own meter can create additional charges up to the separate housekeeping allowance.

Required change: explicitly budget and disclose housekeeping, aggregate it with the question, and persist/emit revised totals when background work completes.

### L4 — High: a model can execute a tool that the user disabled (Tools Hub; Simple tool switches)

`backend/app/tools/__init__.py:31` filters the advertised schemas, but `execute` at line 44 checks only existence, availability and `risky`. It never checks that the tool was offered or enabled for this question. `backend/app/modes/common/tool_loop.py:68` passes every returned tool name straight to the global registry.

Reproduction: call `tool_loop` with **an empty advertised tool list**; a mocked model returns `web_search`. The mocked web tool is still executed with its supplied query (`private text`). This confirms execution bypass without making a real network request. A hallucinated or injected call could therefore trigger external search while Web is off.

Required change: validate every tool name against the run/step's enabled allow-list at execution time and validate its arguments before execution. Returning a tool call must never create permission.

### L5 — Medium: retrying a streamed call leaves the failed draft in the visible answer (C8; correct final output)

`backend/app/llm/client.py:215` immediately invokes the text callback. `_call_with_retries` at line 250 reuses that callback after failure without a reset or per-attempt buffer. The successful `ChatResult.text` contains only the successful attempt, while browser/server view callbacks receive both attempts.

Reproduction: first attempt streams `PARTIAL BAD DRAFT. ` and disconnects; second streams `Correct answer.`. Returned text is `Correct answer.`, but callback-visible text is **`PARTIAL BAD DRAFT. Correct answer.`**. The engine may replace the final view later when it notices a mismatch, but the failed content is visible in the meantime and lower-level consumers remain inconsistent.

Required change: add an explicit replacement/reset event when a streamed attempt is abandoned, or buffer attempts until a successful terminal event.

### L6 — Medium: truncated streams can be recorded as successful, free responses (C8, C20; complete cost/time/token logs)

`backend/app/llm/client.py:187` returns after EOF without requiring a finish reason or `[DONE]`. `raw_usage` starts as `None`; `_usage_from` at line 138 turns missing usage into zero prompt tokens, zero completion tokens and zero cost. `_call_with_retries` logs this as success.

Reproduction: HTTP 200 SSE containing a single partial content event, no finish reason, no usage and no `[DONE]` returns **text `partial`, finish `""`, cost $0, input tokens 0, output tokens 0**. No retry/fallback is requested. Transport errors after partial generation similarly log zero-cost failed attempts at line 260, and cancellation is not logged through that `LLMError` handler.

Required change: validate stream completion, retain/reconcile partial-generation usage, and mark unavailable usage as unknown rather than zero. Recover provider usage by request ID where possible; otherwise reserve/estimate conservatively with an explicit warning.

### L7 — Medium: authentication or exhausted credits aborts before trying the other provider (C8)

`backend/app/llm/client.py:156` marks HTTP 401/402 fatal; line 297 raises immediately instead of proceeding along the fallback chain. A valid second provider does not help if the selected provider's credentials become invalid or credits run out.

Reproduction: the primary mock returns 401; a healthy NVIDIA fallback exists in the registry. The attempted model list contains **only the primary**. The fallback is never called.

Required change: treat provider-wide failures as a reason to skip that provider's remaining models while still trying authorized models on another provider. Do not retry the rejected key.

## Missing or partial specification features

| Requirement | Evidence | Status |
|---|---|---|
| Docker code sandbox (Part 1 §9) | `backend/app/tools/code_runner.py:25` sets `available=False`; the body only returns an unavailable message | Missing, safely disabled |
| C11 risky tool ask/allow/deny flow | `tools.specs_for` omits all risky tools; `tools.execute` rejects them unconditionally. There is no available permission workflow in this hub | Missing, safe refusal rather than specified functionality |
| PNG deliverable / PNG skill (stage 5 / shared Skills Hub) | `backend/app/modes/planner/plan.py:17` format whitelist excludes PNG; `backend/app/output/artifacts.py:36` has PDF/HTML/code/Markdown/plain text paths only; skills catalog has no PNG skill | Missing |
| C21 final safety/format failure repaired once then plain text | `backend/app/output/final_check.py:7` only redacts secret-looking strings and replaces an empty answer. `artifacts.py` catches rendering exceptions and immediately writes plain text | Partial; no general format validation or one-repair attempt |
| Provider prompt-cache accounting (Part 2 §3) | `backend/app/llm/registry.py:81` hardcodes all cached reads at 10%, with no cache-write multiplier; `_prepare_messages` only places a 5-minute marker on the first system message | Partial; provider-reported actual `usage.cost` mitigates successful OpenRouter calls, but estimates/fallback accounting omit the spec's differing rates and optional 1-hour cache |
| Complete per-step logs | Successful model calls and handled model errors have model/tokens/cost/time rows. Tool invocations only create transient UI events, not durable tool timing/result records in a trace | Partial |

The root audit should also check whether Planner's final Checker inspects the actual document: `modes/planner/assemble.py` builds/emits the artifact and returns a short `PDF is ready` message, so checking that confirmation would not validate the deliverable.

## Implemented correctly in the inspected paths

- One common OpenAI-style adapter serves both providers.
- Retriable transport/timeout/429/5xx errors get three attempts (initial + two retries) with bounded backoff; ordinary nonfatal failures proceed to a short fallback chain.
- Registry data carries provider/company/prices/context/tool/image/reasoning flags; live OpenRouter loading, a disk cache, static NVIDIA metadata, provider availability and capable fallback filtering are present.
- Successful provider-reported usage is recorded with stage, model, provider, input/output/cache/reasoning tokens, money and elapsed time; reports aggregate model/stage totals. Ratings persist in message records.
- Model-supplied code is not executed on the host. Arithmetic is AST-restricted; the full code runner is unavailable.
- `read_webpage` requires an exact URL previously returned by the run's search and checks public-address resolution before each request/redirect. This is useful isolation, although DNS resolution is checked separately from the actual HTTP connection rather than pinned.
- File-search tools are scoped to a chat; external material is explicitly wrapped as data. Skills are repository-owned files, parsed with safe YAML, selected within a token budget and injected into prompts.
- Tools are capped at ten actual executions per `tool_loop` invocation. The code does not globally cap executions across retries/multiple Planner steps, and after the cap it relies on the model to obey the absence of tool schemas; the enclosing run timeout/budget provides the ultimate exit.
- Artifact filenames are sanitized, IDs random, model text HTML-escaped, content secret-redacted, and format exceptions fall back to a text file.

## Verification limits

Actual provider availability, model existence/capabilities, API permissions, upstream prices, live web search, cross-provider inference and paid output quality were not exercised. Those cannot be certified from cached model data or mocked tests. The code-sandbox and PNG gaps are visible implementation facts, not environmental test failures. Dollar amounts in the reasoning/race reproductions use deliberately chosen mock rates to make the control-flow defect easy to inspect.
