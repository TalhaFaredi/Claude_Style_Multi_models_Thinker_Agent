# Prompts

Every system prompt used by an agent, sub-agent or team lives here, one Markdown file per prompt. Python code never contains prompt text; it calls:

```python
from app import prompts
prompts.render("thinker/judge")                                          # a fixed prompt
prompts.render("planner/step", goal=g, number=2, total=4, task=t, done_test=d, prior="", feedback="")
```

## File format

```markdown
<!-- Where this prompt is used. This comment is removed when the prompt is loaded. -->
The prompt text. $placeholder is filled by render(); write $$ for a literal dollar sign.
```

- A missing placeholder raises `KeyError`, so a typo fails `tests/test_hubs.py` instead of a live run.
- `prompts.names()` lists every prompt; `prompts.placeholders(name)` lists the names a prompt needs.
- `prompts.catalog()` and `GET /api/prompts` show the shipped template text with its role. `$placeholders` are displayed literally; no user's messages, files, memory, tool outputs or provider credentials are returned.
- Edit a prompt and restart the server (prompts are cached after the first load).

## Map

| Prompt | Who uses it | Spec |
|---|---|---|
| `shared/system_rules` | first system message of every answer, team agent and plan step | stable cached prefix |
| `shared/documents_header` | in front of the user's files in the window | C30, C31, C44 |
| `gateway/refusal` | Input Gateway reply to an unsafe request | C1 |
| `router/route` | Auto mode's small model | C2, C5, C6 |
| `checker/check` | the Checker | stage 4, C19, C32 |
| `simple/retry` | Simple: answer again with the checker's feedback | stage 4 retry |
| `thinker/agent` | added to each team agent's system message | section 5 |
| `thinker/roles/*` | Solver, Critic, Fact-checker, Simplifier, Devil's advocate, Independent | "each copy gets its own role" |
| `thinker/board` | together style: the shared board | T8 |
| `thinker/judge` | together style: do they agree? | T7 |
| `thinker/composer` · `composer_retry` | merge the answers; retry the composer only | C14, T9, T10 |
| `planner/plan_writer` | write or re-write the plan | section 6, C15, C17 |
| `planner/step` | the task one step gets | section 6 |
| `planner/assemble` + `form_text` / `form_document` / `form_code` / `form_png` | the final deliverable | step 5 |
| `memory/facts` | Memory Writer | C39, C41 |
| `memory/ledger` · `summary` · `summary_redo` · `merge` | checked compaction | Part 2 section 7 |
| `files/ocr_scan` · `chart` · `card` · `query_rewrite` | attachment pipeline | C25, C27, Part 2 section 5 |
| `skills/header` | wraps the skills picked for a question | Skills Hub |

## Writing rules

- Say what to do in short, numbered or bulleted lines. Cheap models follow plain instructions best.
- Every prompt that sees outside text (files, web pages, chat history, imports) says it is **DATA, not instructions**.
- JSON prompts end with the exact JSON shape and "Return JSON only".
