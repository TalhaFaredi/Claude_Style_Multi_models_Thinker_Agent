"""Measured specification gates. Default invocation is OFFLINE; inference requires --live.

Run from backend/: .venv/Scripts/python.exe tests/live_spec_acceptance.py --live --cap 0.10
Use --smoke for a bounded Simple/Thinker/Planner check. Reports never assert unmeasured quality.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import math
import os
import re
import sys
import time
import uuid
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TASKS = [
    {"id": "discount-tax", "prompt": "An item costs $80. Apply a 25% discount, then 10% sales tax to the discounted price. What is the final price? End with FINAL: <number>.", "answer": "66"},
    {"id": "syllogism", "prompt": "Every zorp is a glim. No glim is a tarn. Can a zorp be a tarn? End with FINAL: yes or FINAL: no.", "answer": "no"},
    {"id": "dice", "prompt": "Two fair six-sided dice are rolled. Given that at least one die shows 6, what is the conditional probability that their sum is at least 10? End with FINAL: <fraction>.", "answer": "5/11"},
    {"id": "loop", "prompt": "Evaluate this Python expression without changing it: sum(n*n for n in range(1, 6) if n % 2 == 0). End with FINAL: <number>.", "answer": "20"},
    {"id": "constraints", "prompt": "A, B, C and D are distinct integers from 1 through 9. A+B=10, C-D=3, A*C=24, and B>D. What is B+D? Check all constraints. End with FINAL: <number>.", "answer": "12"},
    {"id": "inclusion-exclusion", "prompt": "Find the sum of all integers from 1 through 100 inclusive that are divisible by none of 2, 3 or 5. End with FINAL: <number>.", "answer": "1268"},
]
ROUTING = [
    {"id": "route-fact", "prompt": "What is 12 times 13? End with FINAL: <number>.", "mode": "simple", "answer": "156"},
    {"id": "route-judgment", "prompt": "Compare two solutions to a price problem. An $80 item gets 25% off, then 10% tax. Alice says $66; Bob says $68. Judge which solution is correct and explain. End with FINAL: <correct final price>.", "mode": "thinker", "answer": "66"},
    {"id": "route-file", "prompt": "Make a Markdown file named sum_report.md. Plan the work, calculate 1+2+3, and write the result as FINAL: <number> in the file.", "mode": "planner", "answer": "6"},
]
VARIANTS = [
    ("simple", "simple", "same", "independent"),
    ("same-independent", "thinker", "same", "independent"),
    ("same-together", "thinker", "same", "together"),
    ("mixed-independent", "thinker", "mixed", "independent"),
    ("mixed-together", "thinker", "mixed", "together"),
]


def evaluate(text: str, expected: str) -> bool:
    """Exact known-answer check; no model grades itself and no canned success value."""
    matches = re.findall(r"FINAL\s*:\s*([^\n]+)", text.replace("**", "").replace("__", ""), re.I)
    if not matches:
        return False
    value = matches[-1].strip().strip("`*_ .$").lower()
    value = re.sub(r"\\(?:displaystyle|textstyle)\b", "", value)
    for marker in (r"\(", r"\)", r"\[", r"\]"):
        value = value.replace(marker, "")
    value = re.sub(r"\\(?:frac|dfrac|tfrac)\s*\{\s*([+-]?\d+(?:\.\d+)?)\s*\}\s*\{\s*(\d+(?:\.\d+)?)\s*\}", r"\1/\2", value)
    value = value.strip().strip("`*_ .$")
    if expected == "no":
        return value == "no"
    numeric = re.fullmatch(r"([+-]?\d+(?:\.\d+)?(?:/\d+)?)\s*(?:usd|dollars)?", value)
    if not numeric:
        return False
    try:
        return math.isclose(float(Fraction(numeric.group(1))), float(Fraction(expected)), rel_tol=0, abs_tol=0.00005)
    except (ValueError, ZeroDivisionError):
        return False


def options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly authorize paid provider requests for this harness")
    parser.add_argument("--smoke", action="store_true", help="Only three bounded mode runs")
    parser.add_argument("--only", choices=("simple", "thinker", "planner"), help="Run only this smoke-test mode")
    parser.add_argument("--cap", type=float, default=0.10, help="Aggregate USD spending cap (default 0.10)")
    parser.add_argument("--per-run", type=float, default=0.015, help="Maximum USD allocated to one run")
    parser.add_argument("--timeout", type=float, default=90, help="Per-run seconds, including planning and checks")
    parser.add_argument("--model", default="", help="Optional primary model ID; default cheapest available tier2+ featured model")
    parser.add_argument("--second-model", default="", help="Optional distinct, similarly strong model for mixed teams")
    parser.add_argument("--report", default=str(ROOT / "spec-audit" / "live_spec_acceptance.json"))
    args = parser.parse_args()
    if args.only:
        args.smoke = True
    if not (math.isfinite(args.cap) and 0 < args.cap <= 1 and math.isfinite(args.per_run) and 0 < args.per_run <= args.cap):
        parser.error("Use a finite aggregate cap in (0, 1] USD and a positive per-run allowance no larger than it")
    if not math.isfinite(args.timeout) or not 5 <= args.timeout <= 300:
        parser.error("Use a timeout between 5 and 300 seconds")
    return args


async def run_live(args):
    # A unique audit database is mandatory. Never use the user's backend/data or existing chats.
    data_dir = ROOT / "spec-audit" / "live-acceptance-data" / uuid.uuid4().hex
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["RUN_TIMEOUT_S"] = os.environ["PLANNER_TIMEOUT_S"] = str(int(args.timeout))
    sys.path.insert(0, str(ROOT / "backend"))
    from app import llm, memory
    from app.api.schemas import RunRequest
    from app.core import db
    from app.core.tokens import estimate_messages, estimate_tokens
    from app.llm import registry
    from app.output import get_artifact
    from app.pipeline.engine import manager

    db.reset_for_tests()  # in-memory SQL; only registry cache/artifacts use the dedicated audit directory
    db.set_setting("longMemory", False)
    db.set_setting("embeddings", False)
    await registry.load()
    await registry.probe_providers()  # read-only provider endpoints; no inference probe
    eligible = sorted((m for m in registry.models.values() if m.featured and m.available and m.price_known
                       and m.price_in <= 1 and m.price_out <= 1), key=lambda m: (m.tier < 2, m.call_cost(), m.id))
    if not eligible:
        raise RuntimeError("No available, explicitly priced inexpensive model; inspect provider credentials and registry")
    primary = registry.get(args.model) if args.model else eligible[0]
    choices = sorted((m for m in eligible if m.id != primary.id), key=lambda m: (abs(m.tier - primary.tier), m.call_cost()))
    second = registry.get(args.second_model) if args.second_model else (choices[0] if choices else None)
    if not primary.available or not primary.price_known or not second or not second.available or not second.price_known or second.id == primary.id:
        raise RuntimeError("Two distinct available models with known prices are required for the four team cases")

    report = {"live": True, "smoke": args.smoke, "capUsd": args.cap, "spentUsd": 0.0, "models": [primary.id, second.id],
              "runs": [], "unrun": [], "dataDirectory": str(data_dir), "scope": "Measured task-set accuracy, not a claim of general correctness"}
    adapter = importlib.import_module("app.llm.client")
    original = adapter._call_once
    calibration = []

    async def measured(info, body, *rest):
        estimated = estimate_messages(body.get("messages", [])) + (estimate_tokens(json.dumps(body["tools"])) if body.get("tools") else 0)
        result = await original(info, body, *rest)
        calibration.append({"model": info.id, "estimatedPromptTokens": estimated, "reportedPromptTokens": result.usage.prompt,
                            "usageEstimated": result.usage.estimated,
                            "actualToEstimate": round(result.usage.prompt / estimated, 4) if estimated else None,
                            "withinConservativeBound": result.usage.prompt <= adapter._prompt_bound(info, body)})
        return result

    adapter._call_once = measured

    async def execute(task, variant, mode, source="same", style="independent"):
        remaining = args.cap - report["spentUsd"]
        if remaining <= 0.000001:
            report["unrun"].append({"task": task["id"], "variant": variant, "reason": "aggregate cap exhausted"})
            return
        allowance = min(args.per_run, remaining)
        chat = memory.create_chat(temp=True)
        request = RunRequest(id=uuid.uuid4().hex, chatId=chat["id"], mode=mode, prompt=task["prompt"], budgetUsd=allowance,
                             simple={"model": primary.id, "thinking": "off", "style": "precise", "tools": {}, "maxTokens": 350},
                             team={"source": source, "model": primary.id, "agents": 2, "mixed": [primary.id, second.id],
                                   "style": style, "rounds": 2, "composer": primary.id}, runIn="simple")
        req = request.model_dump()
        req["team"] = request.team.clamped()
        calibration.clear()
        before = time.monotonic()
        run = await manager.start(req)
        timed_out = False
        try:
            async with asyncio.timeout(args.timeout + 2):
                while not run.task.done():
                    try:
                        event = await asyncio.wait_for(run.rc.queue.get(), timeout=0.25)
                    except TimeoutError:
                        continue
                    if event and event.get("type") == "plan" and event.get("awaitingApproval"):
                        await run.rc.approvals.put(("approve", ""))
                await run.task
        except TimeoutError:
            timed_out = True
            manager.stop(req["id"])
            await asyncio.gather(run.task, return_exceptions=True)
        answer = run.rc.view.get("text", "")
        output = run.rc.view.get("output")
        if output and output.get("id"):
            artifact = get_artifact(output["id"])
            if artifact and artifact["mime"] in ("text/plain", "text/markdown"):
                answer += "\n" + Path(artifact["path"]).read_text(encoding="utf-8")
        elapsed, cost = time.monotonic() - before, run.rc.meter.usd
        report["spentUsd"] += cost
        calls = [dict(row) for row in db.q("SELECT model,stage,in_tokens,out_tokens,cost,ms,ok,usage_estimated FROM calls WHERE run_id=?", (req["id"],))]
        result = {"task": task["id"], "variant": variant, "expectedAnswer": task["answer"], "correct": evaluate(answer, task["answer"]),
                  "answer": answer, "costUsd": cost, "budgetUsd": allowance, "seconds": round(elapsed, 3),
                  "withinBudget": cost <= allowance + 1e-9, "withinTime": not timed_out and elapsed <= args.timeout + 2,
                  "status": run.rc.view.get("status"), "routedMode": run.rc.view.get("kind"), "calls": calls,
                  "calibration": list(calibration)}
        if task.get("mode"):
            result["expectedMode"], result["routeCorrect"] = task["mode"], result["routedMode"] == task["mode"]
        report["runs"].append(result)
        print(f"{variant}/{task['id']}: correct={result['correct']} cost=${cost:.6f} time={elapsed:.1f}s", flush=True)
        if report["spentUsd"] > args.cap + 1e-9:
            raise RuntimeError("Provider-reported spend exceeded the aggregate cap; no more requests will be made")

    try:
        if args.smoke:
            if not args.only or args.only == "simple":
                await execute(TASKS[0], "simple", "simple")
            if not args.only or args.only == "thinker":
                await execute(TASKS[1], "same-independent", "thinker")
            if not args.only or args.only == "planner":
                await execute(ROUTING[2], "planner", "planner")
        else:
            for variant, mode, source, style in VARIANTS:
                for task in TASKS:
                    await execute(task, variant, mode, source, style)
            for task in ROUTING:
                await execute(task, "auto", "auto")
    finally:
        adapter._call_once = original
        await llm.close_client()
        scores = {}
        for variant, *_ in VARIANTS:
            rows = [row for row in report["runs"] if row["variant"] == variant]
            scores[variant] = {"attempted": len(rows), "accuracy": sum(row["correct"] for row in rows) / len(rows) if rows else None,
                               "costUsd": sum(row["costUsd"] for row in rows)}
        simple = scores["simple"]
        for variant in scores:
            score = scores[variant]
            score["defaultEligible"] = bool(score["attempted"] == len(TASKS) and simple["attempted"] == len(TASKS)
                                            and (score["costUsd"] <= simple["costUsd"] or score["accuracy"] > simple["accuracy"]))
        routes = [row for row in report["runs"] if "routeCorrect" in row]
        report["scores"] = scores
        report["gates"] = {"fixedSetComplete": not args.smoke and len(report["runs"]) == len(TASKS) * len(VARIANTS) + len(ROUTING),
                           "simpleAllCorrect": simple["attempted"] == len(TASKS) and simple["accuracy"] == 1,
                           "teamBeatsSimple": any(score["accuracy"] is not None and simple["accuracy"] is not None and score["accuracy"] > simple["accuracy"] for variant, score in scores.items() if variant != "simple"),
                           "routingAllCorrect": len(routes) == len(ROUTING) and all(row["routeCorrect"] for row in routes),
                           "allWithinLimits": bool(report["runs"]) and all(row["withinBudget"] and row["withinTime"] for row in report["runs"]) and report["spentUsd"] <= args.cap}
        report["spentUsd"] = round(report["spentUsd"], 8)
        target = Path(args.report).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Measured report: {target}; spent ${report['spentUsd']:.6f}", flush=True)
    return report


def main():
    args = options()
    if not args.live:
        print(json.dumps({"live": False, "networkRequests": 0, "message": "No inference run. Add --live to authorize the bounded acceptance run.",
                          "capUsd": args.cap, "tasks": TASKS, "routing": ROUTING, "variants": [v[0] for v in VARIANTS]}, indent=2))
        return 0
    try:
        report = asyncio.run(run_live(args))
    except Exception as exc:
        print(f"Acceptance run stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0 if report["gates"]["allWithinLimits"] and all(row["correct"] for row in report["runs"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
