---
name: prompt-engineering
description: Write or improve prompts and system prompts for AI models.
triggers: [prompt, system prompt, write a prompt, improve my prompt, prompt engineering, instructions for an ai, llm prompt]
modes: [simple, thinker, planner]
source: written for this app
---
A good prompt states, in this order:
1. Role and goal: who the model is and what success looks like.
2. Context: the facts it needs, marked as data (for example inside <documents> tags).
3. Task steps: numbered, one action each.
4. Constraints: length, tone, what to avoid, what to do when unsure ("say you don't know").
5. Output format: an exact example or schema.
Prefer positive instructions ("write short sentences") over prohibitions, and one example over many rules.
Never put secrets in a prompt. Give the improved prompt in one code block, then 2 to 3 lines on what changed.
