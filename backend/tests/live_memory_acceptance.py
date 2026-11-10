"""Opt-in 50-fact compaction/import recall gate, with a shared hard inference budget.

Default invocation makes no network requests. Run from backend/ with --live --cap 0.005.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]


async def run(args):
    os.environ["DATA_DIR"] = str(ROOT / "spec-audit" / "live-memory-data" / uuid.uuid4().hex)
    sys.path.insert(0, str(ROOT / "backend"))
    from app import llm, memory
    from app.core import config, db
    from app.core.costmeter import CostMeter
    from app.memory import portability
    db.reset_for_tests()
    db.set_setting("embeddings", False)
    db.set_setting("longMemory", False)
    db.set_setting("windowCap", 64000)
    await llm.registry.load()
    await llm.registry.probe_providers()
    candidates = [m for m in llm.registry.models.values() if m.available and m.price_known and m.featured]
    if not candidates:
        raise RuntimeError("No available priced model. No inference was run.")
    model = llm.registry.get(config.WRITER_MODEL)
    if not model.available:
        model = min(candidates, key=lambda m: m.call_cost(5000, 1600))
    meter = CostMeter(args.cap)
    chat = memory.create_chat("Live 50-fact acceptance", temp=True)
    ctx = llm.CallContext(meter=meter, chat_id=chat["id"], run_id="memory-acceptance")
    expected = {f"Fact{i:02d}": f"ZX-{7100 + i * 13}" for i in range(1, 51)}
    for key, value in expected.items():
        memory.add_message(chat["id"], "user", f"Record {key} = {value}.")
        memory.add_message(chat["id"], "assistant", f"Recorded {key}.")
    report = {"live": True, "capUsd": args.cap, "model": model.id, "facts": 50,
              "compaction": None, "recall": [], "spentUsd": 0.0, "passed": False}

    async def recall(cid, stage):
        question = "Return JSON only with the exact values previously recorded for Fact01 through Fact50. Use each FactNN as a key and its ZX code as the value. If a value is unknown, use null."
        built = await memory.build(cid, question, model.id, ctx=ctx, with_files=False)
        messages = list(built.messages)
        messages[0] = {"role": "system", "content": messages[0]["content"] + "\nExtract the recorded facts exactly. Return one JSON object without prose."}
        response = await llm.complete(model.id, messages, stage=stage, ctx=ctx, temperature=0, max_tokens=1600, thinking="off")
        values = llm.parse_json(response.text)
        if isinstance(values, dict) and isinstance(values.get("facts"), dict):
            values = values["facts"]
        values = values if isinstance(values, dict) else {}
        correct = [key for key, value in expected.items() if str(values.get(key, "")).strip() == value]
        return {"stage": stage, "correct": len(correct), "total": 50, "recall": len(correct) / 50,
                "missing": [key for key in expected if key not in correct], "response": response.text,
                "contextPercent": built.percent}

    try:
        result = await memory.compact(chat["id"], model.id, ctx)
        report["compaction"] = {"ok": result.ok, "messages": result.summarized, "reason": result.reason}
        if not result.ok:
            raise RuntimeError("Checked compaction did not succeed; originals were preserved")
        report["recall"].append(await recall(chat["id"], "acceptance:after_compaction"))
        imported = await portability.import_chat(portability.build_export(chat["id"]))
        report["recall"].append(await recall(imported["chatId"], "acceptance:after_import"))
        report["passed"] = all(row["recall"] >= .95 for row in report["recall"])
    except Exception as exc:
        from app.core.privacy import safe_message
        report["error"] = f"{type(exc).__name__}: {safe_message(exc)}"
    finally:
        report["spentUsd"] = round(meter.usd, 8)
        report["withinBudget"] = meter.usd <= args.cap + 1e-9
        report["estimatedCharges"] = meter.estimated_calls
        report["passed"] = report["passed"] and report["withinBudget"]
        await llm.close_client()
        path = Path(args.report).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "spentUsd": report["spentUsd"],
                          "recall": [{"stage": row["stage"], "correct": row["correct"], "total": 50} for row in report["recall"]],
                          "error": report.get("error"), "report": str(path)}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cap", type=float, default=.005)
    parser.add_argument("--report", default=str(ROOT / "spec-audit" / "live-memory-2026-11-10.json"))
    args = parser.parse_args()
    if not math.isfinite(args.cap) or not 0 < args.cap <= 1:
        parser.error("Use a finite cap in (0,1] USD")
    if not args.live:
        print("No network requests. Add --live to run the isolated 50-fact gate within the specified budget.")
        return 0
    return 0 if asyncio.run(run(args))["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
