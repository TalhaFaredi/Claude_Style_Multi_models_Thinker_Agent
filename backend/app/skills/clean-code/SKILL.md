---
name: clean-code
description: Write small, readable, working code with the edge cases handled.
triggers: [write a function, write a script, code, script, function, python, javascript, typescript, sql, regex, api, class]
modes: [simple, thinker, planner]
formats: [code]
source: written for this app
---
- Confirm the language, inputs and output in one line, then write the code.
- One complete, runnable block: imports included, no "..." placeholders.
- Clear names, small functions, comments only where the reason is not obvious.
- Validate inputs and handle the edge cases (empty, missing, wrong type, too large).
- Never hard-code secrets; read them from environment variables.
- Prefer the standard library and well-known packages; name any package to install.
- After the code: how to run it, and one example input with its output.
