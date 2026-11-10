---
name: verification-before-completion
description: Check the result against the request before calling it done.
triggers: [double-check, double check, check my, is this correct, proofread, verify this, verify my]
hints: [verify, make sure, confirm, correct]
modes: [simple, thinker, planner]
source: inspired by https://github.com/obra/superpowers (verification-before-completion skill, MIT); rewritten for this app
---
Before you finish:
- Re-read the request and tick off every part it asked for. Name anything you could not do.
- Re-check every number, unit, name and date against its source or calculation.
- For code: does it run as written (imports, names, syntax)? Give the command to try it.
- For claims: is each one supported, or clearly marked as uncertain?
Report what you verified and how. Never say "done" or "fixed" for something you did not check.
