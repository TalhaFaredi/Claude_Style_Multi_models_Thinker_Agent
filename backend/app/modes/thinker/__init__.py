"""Mode B: Thinker. 2 to 5 agents think about the same question; one composer merges their answers.

    team.py      agents: same model with roles and temperatures, or different models; progress output
    rounds.py    one round in parallel, the shared board, the judge (T6 to T8)
    composer.py  merge, Checker, composer-only retry (C14, T9, T10)
    run.py       the mode, also used by Planner team steps
"""
from app.modes.thinker.run import run_thinker
from app.modes.thinker.team import Agent, build_agents, team_line

__all__ = ["run_thinker", "Agent", "build_agents", "team_line"]
