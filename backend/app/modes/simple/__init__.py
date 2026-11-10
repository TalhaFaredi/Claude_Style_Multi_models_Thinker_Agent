"""Mode A: Simple. One model answers and uses tools when it needs them.

    run.py           the mode: build the window, tool loop, Checker with retries
    model_choice.py  C9: switch to a tool-capable model when tools are on
"""
from app.modes.simple.run import run_simple

__all__ = ["run_simple"]
