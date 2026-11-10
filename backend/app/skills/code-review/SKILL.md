---
name: code-review
description: Review code for bugs, security risks and clarity, most important first.
triggers: [review my code, code review, review this code, refactor, security review, vulnerability, vulnerabilities, code smell, pull request]
modes: [simple, thinker, planner]
formats: [code]
source: inspired by https://github.com/obra/superpowers (requesting-code-review / receiving-code-review skills, MIT); rewritten for this app
---
Order findings by severity: correctness bugs, security, data loss, performance, then readability.
For each finding give: where (function or line), what goes wrong with a concrete input, and the fix.
Security checklist: injection (SQL, shell, HTML), secrets in code or logs, missing input checks,
unsafe file paths, missing auth checks, unbounded loops or sizes.
Do not report style nits as bugs. Say what is good in one line, and do not invent problems to look thorough.
End with the 1 to 3 changes that matter most.
