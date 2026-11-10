"""calculator: exact arithmetic for the model, without running any code.

Small models make arithmetic slips; this tool evaluates a math expression safely. It parses the
expression into a syntax tree and allows only numbers, + - * / // % **, brackets and a short list of
math functions. Names, attributes, calls to anything else, and huge powers are refused, so it can never
run code or hang the server. This is the safe part of the spec's "code runner"; a full code sandbox
needs Docker (see code_runner.py).
"""
from __future__ import annotations

import ast
import math
import operator

from app.tools.base import Tool, ToolResult, ToolRun

MAX_LEN = 300
MAX_POWER = 10_000
MAX_MAGNITUDE = 1e100

_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "log": math.log, "log10": math.log10, "log2": math.log2, "exp": math.exp, "sin": math.sin, "cos": math.cos,
          "tan": math.tan, "asin": math.asin, "acos": math.acos, "atan": math.atan, "floor": math.floor, "ceil": math.ceil,
          "abs": abs, "round": round, "min": min, "max": max, "factorial": math.factorial}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


class CalcError(ValueError):
    pass


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > MAX_POWER or abs(left) > MAX_MAGNITUDE):
            raise CalcError("power too large")
        out = _BINARY[type(node.op)](left, right)
        if isinstance(out, (int, float)) and abs(out) > MAX_MAGNITUDE ** 3:
            raise CalcError("result too large")
        return out
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        args = [_eval(a) for a in node.args]
        if node.func.id == "factorial" and (len(args) != 1 or args[0] > 500):
            raise CalcError("factorial argument too large")
        return _FUNCS[node.func.id](*args)
    raise CalcError(f"not allowed: {type(node).__name__}")


def calculate(expression: str) -> float:
    expr = expression.strip().replace("^", "**").replace(",", "")
    if not expr or len(expr) > MAX_LEN:
        raise CalcError("expression is empty or too long")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise CalcError("not a valid math expression") from e
    return _eval(tree)


async def _run(args: dict, state: ToolRun) -> ToolResult:
    expr = str(args.get("expression", ""))
    try:
        value = calculate(expr)
    except (CalcError, ZeroDivisionError, OverflowError, ValueError, TypeError) as e:
        return ToolResult(f"Could not calculate: {e}", ok=False, done_label="Calculation failed")
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        value = int(value)
    shown = f"{value:.10g}" if isinstance(value, float) else str(value)
    return ToolResult(f"{expr.strip()} = {shown}", done_label="Calculated")


TOOL = Tool(
    name="calculator",
    setting="code",
    description="Evaluate a math expression exactly, e.g. '(48250*1.07)/12' or 'sqrt(2)*pi'. Use it for any non-trivial arithmetic.",
    parameters={"type": "object", "properties": {"expression": {"type": "string", "description": "A math expression"}}, "required": ["expression"]},
    run=_run,
    running_label=lambda a: f"Calculating {str(a.get('expression', ''))[:40]}",
)
