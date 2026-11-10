"""The five-stage pipeline every question passes (spec Part 1 Figure 1).

    gateway.py   1. Input Gateway: safety check (C1)
    router.py    2. Mode Router: the user's mode or Auto (C4 to C6), one clarifying question (C2)
    estimate.py     Budget Guard's price before the run (C7)
    (app/modes)  3. Simple | Thinker | Planner
    checker.py   4. Checker: every answer and every plan step (C19, C32)
    (app/output) 5. Output Builder: final safety and format check (C21)
    engine.py    runs the stages, the run manager, auto-compaction, the Memory Writer
    runtime.py   per-run state and the event stream to the browser
This file imports nothing on purpose: the modes import the checker, and the engine imports the modes.
"""
