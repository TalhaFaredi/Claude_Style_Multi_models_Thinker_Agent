# Multi-Mode AI Assistant: flow, safety, memory and file addendum (v3)

Updated November 11, 2026. This addendum follows the v2 addendum (A1 to A6) and records what the November 11 flow audit changed. It must be read together with the original 15-page specification and the v2 addendum. Where this addendum and an earlier text differ, this addendum wins. Fixed safety limits (2 to 5 agents, 1 to 3 rounds, 10 tool calls, 2 retries, 2 re-plans, 20 plan steps) and the approved-budget rules are unchanged.

Status of verification: every item below is covered by offline tests (backend 152 passed, frontend 38 passed, TypeScript check clean). Nothing in this addendum has been measured against live models yet; section A19 lists what QA should measure.

## A7. Follow-up messages are answered, not questioned (refines C2)

- The router reads only the new message, so a short follow-up such as "make it shorter" looks unclear to it. The router therefore never asks a clarifying question when the chat already holds an assistant answer, or when files are attached. The answering model sees the conversation and asks for itself if it truly needs to.
- "Existing conversation" means any earlier non-empty assistant message in the chat. The earlier 1,500-token threshold is removed because it missed young chats.
- On a first message with no files, C2 is unchanged: the router asks one short question only when it reports `understood = false`.

Acceptance: after one answered turn, a vague second message produces an answer and no clarify event. A first vague message still produces exactly one question.

## A8. Safety: a second opinion before refusing (refines C1)

- The keyword gateway still refuses clearly harmful requests before any model call.
- When the small router model reports `safe = false`, the stronger Checker model (`CHECKER_MODEL`) is asked the same question (stage `router:safety`). The refusal stands unless that second model clearly answers `safe = true`. An unreadable or failed second opinion keeps the refusal.
- This path runs only on a refusal, so it adds no cost to normal questions.
- Limit: this reduces wrong refusals. It does not reduce missed harmful requests. A dedicated moderation model is still recommended before public use.

Acceptance: a legitimate request wrongly flagged by the small model is answered when the second model says safe, and is refused when the second model says unsafe or returns invalid output.

## A9. Checker honesty and retry wording

- "The answer could not be checked" (checker unavailable, unreadable, or switched off) is reported as **"This answer was not checked: ..."**. "The checker found a problem" is reported only when the checker actually returned a failing verdict. This applies to Simple mode and to the Thinker composer.
- The Simple retry prompt lists unsupported claims as plain text and says to rely on documents or search results only if some were supplied. Without sources the model answers from its own knowledge instead of refusing.
- The shared system rules no longer say "do not reveal private context". They state that `<documents>`, `<memory>` and `<summary>` are the user's own data and may be quoted back to the user. This removes a contradiction with the memory rule that caused "I have no access" answers.

Acceptance: a down checker produces the "not checked" warning and never "found a problem". An answer that uses a remembered fact is not refused.

## A10. Thinker team behavior

| Rule | Behavior |
|---|---|
| Revision turn | A revising agent receives the question, then its own earlier answer as an assistant turn, then the shared board as a user turn. The board lists only the other agents. Attached images are no longer dropped. |
| Unchanged | An agent that replies with only "Unchanged" keeps its earlier answer with no extra paid call. |
| Missing "Changed because" | The agent is asked once to restate its answer with the required first line. If it still does not comply, its earlier answer is kept as unchanged. The agent is dropped only when it had no earlier answer. |
| Board and judge excerpts | A long answer is cut to its start and its end (board 1,200 characters, judge 900), because every role prompt ends with the agent's own best answer. A head-only cut hid the conclusion. |
| Judge | The agreement judge may use 40 output tokens, so a short JSON verdict is never cut off. |
| Debate budget guard | The cost check before each extra round assumes 1,600 tokens of added context per agent for the board. |
| Composer | Sees every role's final answer, and after a debate also the round-1 answer. It never sees model names (T9). |

Acceptance: in a 5-agent, 3-round run every agent call carries its own role and temperature (0.3, 0.5, 0.7, 0.9, 1.0), revisions show the agent's own earlier answer, and the composer receives all five roles with model names hidden.

## A11. Thinking display and call accounting (refines A2 and A4)

- A "thinking details" row is added to an answer only when thinking was requested for that call, or when the provider actually returned reasoning text. Router, Checker and judge calls never request thinking and add no row.
- When thinking was requested and the provider returned nothing, the row says the notes were unavailable. Reasoning is never invented.
- If a model spends its whole allowance on reasoning and returns no text, the call is repeated once without thinking. The client then remembers that model and thinking level for the rest of the server run and goes straight to "no thinking", so the wasted call is paid once, not once per agent per question.
- Every call still emits a usage event (model, role or stage, input, output and reasoning tokens, USD, estimated or provider-reported) and the cost line is the sum of those calls.

Acceptance: a Checker call produces a usage event and no thinking row. A requested-but-empty reasoning call produces an "unavailable" row. The second call to a model that ate its answer at "low" is sent without reasoning.

## A12. Live streaming is the default (departs from the original text)

`STREAM_BEFORE_CHECK` now defaults to `1`. The draft streams while it is written, and the Checker can still replace it afterward. Set `STREAM_BEFORE_CHECK=0` to restore the original strict rule that nothing reaches the user before it passes the Checker.

## A13. Optional access token

- New setting `APP_TOKEN`. Empty (the default) leaves the API open, which is safe only on `127.0.0.1`.
- When set, every `/api` route needs the header `Authorization: Bearer <token>`. A wrong or missing token returns 401. The comparison is constant-time.
- Exceptions: browser preflight (OPTIONS) requests, and `GET /api/artifacts/{id}` downloads, which are reached by an unguessable 32-character id because a download link cannot send a header.
- The web app asks for the token once when it receives a 401, keeps it in this browser's local storage, and repeats the request. A build-time `NEXT_PUBLIC_API_TOKEN` can supply it instead.
- Limits: this is one shared password, not user accounts. All users of the same server share one memory, one settings table and one chat list. The app provides no HTTPS; a hosted deployment must sit behind a TLS reverse proxy or the token travels unencrypted.

Acceptance: with a token set, a request without it gets 401, a request with it succeeds, a preflight succeeds, and an unknown artifact id returns 404 rather than 401.

## A14. Memory

- **Ledger gate.** The per-turn ledger call runs only when the message contains a goal, rule, number or preference word (my, our, remember, must, never, always, budget, deadline, goal, decided, prefer, name) or is longer than 240 characters. A plain question costs no ledger call and adds no ledger line. Anything it holds is still captured when its turn is later summarized.
- **Fallback saves statements only.** When the ledger writer fails, the safety net saves sentences that match those words and do not end with a question mark. "What is my best option?" is not stored as a decision.
- **Recall without duplicates.** "As I said earlier" brings back only original messages that a summary has replaced. A message still in the window, and the new question itself, are never sent twice.
- Unchanged: compaction at 95%, the four checked steps, nothing deleted, the 10%, 5% and 35% budgets, and long-term fact replacement with history (C39).

Acceptance: a trivia question produces no `memory:ledger` call. A recall question in a short chat produces no "Original earlier messages" block and the fact appears once in the prompt.

## A15. Text-file decoding

Plain text, Markdown, CSV and code files are decoded as UTF-8 (with or without a byte-order mark), then UTF-16 when it has a byte-order mark, then Windows-1252. Previously any non-UTF-8 file turned accented letters into replacement marks and was misclassified as an unreadable scan needing paid OCR. A file containing null bytes under a text extension is still flagged as unreadable, never shown as text.

Acceptance: a Windows-1252 text file is classified as text and keeps its accented characters. A UTF-16 file is readable. A binary file named `.txt` is flagged.

## A16. Skills and prompt files

- The Skills Hub has 26 skills. Four skills had common single words as triggers and loaded on unrelated questions ("give me a brief answer" loaded the PDF skill; "design a database schema" loaded visual design). Common words moved from `triggers` to `hints` in `data-analysis` and `clean-code`, and `brief` and `design a` were removed from `pdf-report` and `visual-design`. Phrases such as "write code that" and "write a python function" still select `clean-code`.
- The PNG diagram instruction moved from Python into `prompts/planner/form_png.md`, so the prompt viewer shows it. The library now has 35 prompt templates. Three short instructions remain in Python and are not shown in the viewer: the debate "explain your change" follow-up, the Planner's correction message and its exact-page-count note.

## A17. Configuration reference (changes only)

| Variable | Default | Meaning |
|---|---|---|
| `STREAM_BEFORE_CHECK` | 1 | Stream the draft before the Checker finishes. 0 holds it until checked. |
| `APP_TOKEN` | empty | Bearer token for `/api`. Empty means open (local use only). |
| `CORS_ORIGINS` | localhost ports 3000 and 3123 | Set to the real frontend address when hosted. |
| `CHECKER_MODEL` | qwen/qwen3.7-flash | Checker, and the second opinion on a router refusal. |
| `UTILITY_MODEL` | meta-llama/llama-3.1-8b-instruct | Router, agreement judge, search rewrite and rerank. |

## A18. Known limits at this version

- One user per server. No accounts, no per-user memory, no TLS.
- Safety is a keyword list, a small-model verdict and the second opinion in A8. No moderation model.
- Not exercised yet: paid OCR and vision reading of scans and charts, Excel and PowerPoint files, the file-upload screen in a browser, and the search reranker (it can send up to 50 passages to the small model per question; its cost and speed are not measured).
- Run state lives in server memory, so the backend supports a single process only.
- The prompt, skill and wording changes in A7 to A9 and A16 are unmeasured on real models.
- Code quality: no linter or formatter is configured in either project, 192 backend lines exceed 140 characters, and seven functions exceed 60 lines (the longest is the chat import at 185).

## A19. QA checklist for AI performance

1. Follow-ups: five short second messages in an existing chat, each answered without a question.
2. Safety: ten legitimate sensitive-topic questions answered, ten clearly harmful ones refused, and a note of any that went the wrong way.
3. Checker: how often it rejects a correct answer and passes a wrong one, with files, with remembered facts, and without either.
4. Thinker: compare a 3-agent debate against Simple on the same ten questions for answer quality and total cost. Confirm the judge stops rounds when agents agree.
5. Thinking display: notes appear for a thinking-capable model with thinking on, and no thinking row appears for router, Checker or judge calls.
6. Memory: state a fact, ask about it in a new chat, change it, and ask again. Check that the old value is kept as history and the new one is used.
7. Files: one UTF-8 file, one Windows-1252 file, one long file that needs search mode, one scanned PDF, one Excel file and one PowerPoint file. Confirm citations and the cost shown before any paid read.
8. Cost: the total on each answer matches the OpenRouter dashboard within rounding.
9. Token: with `APP_TOKEN` set, the first load asks once, and a wrong token is rejected.
10. Model size: repeat items 1, 3 and 4 on a small and a strong model.
