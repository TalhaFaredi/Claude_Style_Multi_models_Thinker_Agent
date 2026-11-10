"""Opt-in 20-PDF visual reading, retrieval and page-citation gate. No requests without --live."""
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
    os.environ["DATA_DIR"] = str(ROOT / "spec-audit" / "live-file-data" / uuid.uuid4().hex)
    os.environ["VISION_MODEL"] = args.vision_model
    sys.path.insert(0, str(ROOT / "backend"))
    from app import files, llm, memory
    from app.core import config, db
    from app.core.costmeter import CostMeter
    from tests.test_memory_files_acceptance import table_chart_pdf
    db.reset_for_tests()
    db.set_setting("embeddings", False)
    db.set_setting("longMemory", False)
    await llm.registry.load()
    await llm.registry.probe_providers()
    vision = llm.registry.get(args.vision_model)
    if not vision.available or not vision.vision or not vision.price_known:
        raise RuntimeError("The selected priced vision model is unavailable; no inference was run")
    report = {"live": True, "capUsd": args.cap, "visionModel": args.vision_model, "answerModel": config.WRITER_MODEL,
              "fixtures": 20, "results": [], "spentUsd": 0.0, "passed": False}
    def spent():
        return float(db.one("SELECT COALESCE(SUM(cost),0) usd FROM calls")["usd"])
    try:
        for index in range(1, 21):
            chat = memory.create_chat(f"PDF gate {index}", temp=True)
            name = f"manual-{index}.pdf"
            upload = files.ingest(chat["id"], name, table_chart_pdf(index))
            approval = upload["plans"]["auto"]["total"] + .000001
            if approval > args.cap - spent():
                report["stopped"] = "Remaining aggregate budget cannot reserve the next visual reading; no more requests made."
                break
            reading = await files.read_file(chat["id"], upload["fingerprint"], "auto", max_cost=approval)
            remaining = args.cap - spent()
            ctx = llm.CallContext(meter=CostMeter(max(0, remaining)), chat_id=chat["id"], run_id=f"file-gate:{index}")
            question = 'What is the Gearbox capacity in liters, and which quarter has the highest revenue? Return JSON only: {"liters":integer,"quarter":"Q1|Q2|Q3","sources":["file p.N",...]}. Cite the actual file and page for both facts.'
            built = await memory.build(chat["id"], question, config.WRITER_MODEL, ctx=ctx, images_ok=False)
            answer = await llm.complete(config.WRITER_MODEL, built.messages, stage="acceptance:file_answer", ctx=ctx,
                                        temperature=0, thinking="off", max_tokens=250)
            parsed = llm.parse_json(answer.text)
            parsed = parsed if isinstance(parsed, dict) else {}
            citations = parsed.get("sources") or []
            citations = citations if isinstance(citations, list) else [citations]
            cited = " ".join(str(value) for value in citations)
            correct = str(parsed.get("liters")) == str(index + 30) and str(parsed.get("quarter", "")).upper() == "Q2"
            correct_pages = f"{name} p.1" in cited and f"{name} p.2" in cited
            visual = 2 not in reading["card"].get("weakPages", []) and bool(reading["card"].get("charts"))
            report["results"].append({"file": name, "correctFacts": correct, "correctCitations": correct_pages,
                                      "visualReadingSucceeded": visual, "answer": answer.text, "readingCost": reading["cost"]})
            print(f"{index}/20: facts={correct} citations={correct_pages} vision={visual} cumulative=${spent():.6f}", flush=True)
        report["passed"] = len(report["results"]) == 20 and all(row["correctFacts"] and row["correctCitations"] and row["visualReadingSucceeded"] for row in report["results"])
    except Exception as error:
        from app.core.privacy import safe_message
        report["error"] = f"{type(error).__name__}: {safe_message(error)}"
    finally:
        report["spentUsd"] = round(spent(), 8)
        report["withinBudget"] = report["spentUsd"] <= args.cap + 1e-9
        report["passed"] = report["passed"] and report["withinBudget"]
        report["estimatedCharges"] = db.one("SELECT COALESCE(SUM(usage_estimated),0) n FROM calls")["n"]
        await llm.close_client()
        path = Path(args.report).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "tested": len(report["results"]), "spentUsd": report["spentUsd"], "report": str(path), "error": report.get("error")}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cap", type=float, default=.01)
    parser.add_argument("--vision-model", default="google/gemma-3-12b-it")
    parser.add_argument("--report", default=str(ROOT / "spec-audit" / "live-files-2026-11-10.json"))
    args = parser.parse_args()
    if not math.isfinite(args.cap) or not 0 < args.cap <= 1:
        parser.error("Use a finite cap in (0,1] USD")
    if not args.live:
        print("No network requests. Add --live to run the isolated 20-PDF visual/page-citation gate.")
        return 0
    return 0 if asyncio.run(run(args))["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
