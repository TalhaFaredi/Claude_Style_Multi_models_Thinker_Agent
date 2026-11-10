"""Stage 3: the three modes. Only this stage changes with the mode; every mode ends in the same Checker and
Output Builder.

    common/    Result, the tool loop (max 10 tool calls), streaming helpers
    simple/    Mode A: one model + tools
    thinker/   Mode B: 2 to 5 agents, optional debate rounds, one composer
    planner/   Mode C: plan -> approval -> checked steps (Simple or team) -> final output
"""
