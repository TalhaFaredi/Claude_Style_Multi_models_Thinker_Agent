# Skills

Skills are instruction files the Skills Hub adds to a prompt when a question needs them (spec Part 1 section 3). There is one folder per skill, each with a `SKILL.md`, in the same format as the well-known GitHub collections.

## Format

```markdown
---
name: pdf-report                      # kebab-case, same as the folder
description: Structure a report or brief that becomes a PDF or Markdown file.
triggers: [report, pdf, whitepaper]   # distinctive words or phrases: one is enough
hints: [document, summary]            # optional: common words that alone mean little; two are needed
modes: [simple, thinker, planner]     # where it may be used
formats: [pdf, md, txt]               # optional: output formats it serves (pdf, html, md, code, text, plan)
source: inspired by https://github.com/anthropics/skills (pdf skill); rewritten for this app
---
5 to 10 short, concrete instructions. Keep it under about 200 words: it is sent on every use.
```

Quote any YAML value that contains `": "`.

## Selection

`skills.select(text, mode=..., fmt=...)`:
- A format match scores 5, each trigger scores 2 and each hint scores 1. A skill needs at least 2: one trigger, two hints, or a format match.
- Put common words (color, why, list, plan, ideas, current, how many) in `hints`, never in `triggers`. Measured: with them as triggers, a wrong skill was picked in 5 of 22 everyday prompts ("my favorite color is teal" got design advice).
- The best 1 or 2 skills that fit the budget are kept (5% of the window; 600 tokens for a Planner step).
- `skills.render(...)` wraps them in a `<skills>` block. The Context Builder places it **right before the new message**, so the cached start of the prompt does not change.

## Catalog (25)

| Skill | Source |
|---|---|
| deep-thinking, output-format | written for this app (named in the spec) |
| pdf-report | inspired by anthropics/skills `pdf` |
| humanizer | based on blader/humanizer (MIT) and Wikipedia "Signs of AI writing" |
| web-page | inspired by anthropics/skills `frontend-design`, `web-artifacts-builder` |
| visual-design | inspired by anthropics/skills `frontend-design`, `canvas-design`, `theme-factory`, `brand-guidelines` |
| brainstorming, writing-plans, systematic-debugging, test-driven-development, verification-before-completion, code-review | inspired by obra/superpowers (MIT) |
| doc-coauthoring, internal-comms, data-analysis, skill-creator | inspired by anthropics/skills |
| clean-code, web-research, fact-checking, summarization, teaching, math-solving, email-writing, translation, prompt-engineering | written for this app |

No text was copied. Each skill is a short rewrite for cheap models, and the `source` line credits the original. `GET /api/skills` lists them all with token sizes.

## Adding a skill

Create `app/skills/<name>/SKILL.md` and run `python -m pytest tests/test_hubs.py`. No code changes are needed. Skills are repository files only: users and model output can never add or change one.
