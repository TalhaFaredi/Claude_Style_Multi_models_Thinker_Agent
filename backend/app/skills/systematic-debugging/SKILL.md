---
name: systematic-debugging
description: Find the root cause of a bug in four phases before proposing a fix.
triggers: [bug, error, exception, traceback, stack trace, debug, debugging, not working, crash, crashes, fails, failing, broken]
modes: [simple, thinker, planner]
source: inspired by https://github.com/obra/superpowers (systematic-debugging skill, MIT); rewritten for this app
---
1. Read the evidence: the exact error, the line, the input, what changed recently. Quote the key line.
2. Reproduce: state the smallest steps that trigger it, and what should happen instead.
3. Find the root cause: list 2 to 3 hypotheses, the quickest check for each, and which the evidence supports. Fix causes, not symptoms.
4. Fix and verify: give the minimal change, explain why it works, and how to confirm (a test or a command).
Do not guess-and-patch several things at once. If information is missing, say exactly what to run or show.
