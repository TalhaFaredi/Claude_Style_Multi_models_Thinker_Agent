---
name: test-driven-development
description: Write the failing test first, then the smallest code that passes, then clean up.
triggers: [unit test, unit tests, tests, test case, test cases, pytest, jest, vitest, tdd, test coverage]
modes: [simple, thinker, planner]
formats: [code]
source: inspired by https://github.com/obra/superpowers (test-driven-development skill, MIT); rewritten for this app
---
Red, green, refactor:
1. Red: write one test for one behavior. Name it after the behavior ("rejects empty email"). Say why it fails now.
2. Green: write the smallest code that makes it pass. No extra features.
3. Refactor: remove duplication and improve names while the tests stay green.
Cover the happy path, the edges (empty, zero, maximum, wrong type) and one failure case.
Tests must be independent, fast and deterministic: no real network, no shared state, fixed seeds and dates.
