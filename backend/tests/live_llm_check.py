"""Manual live check (costs a fraction of a cent). Run: .venv/Scripts/python.exe -m tests.live_llm_check

Checks: both provider keys, the cheap default models under the privacy setting (providers that do not
store prompts), streaming, thinking on/off, fallback after a bad model id, NVIDIA marked unavailable."""
import asyncio
import os
from pathlib import Path

os.environ.setdefault("DATA_DIR", str(Path(__file__).resolve().parents[1] / "data_test"))

from app import llm  # noqa: E402
from app.core import db  # noqa: E402
from app.core.costmeter import CostMeter  # noqa: E402
from app.llm import CallContext, registry  # noqa: E402

MODELS = [("meta-llama/llama-3.1-8b-instruct", "off"), ("qwen/qwen3.7-flash", "off"), ("qwen/qwen3.7-flash", "low"), ("openai/gpt-oss-120b", "off")]


async def main():
    db.reset_for_tests()
    await registry.load()
    st = await registry.probe_providers()
    print("providers:", {k: (v["ok"], v.get("reason"), v.get("creditRemaining")) for k, v in st.items()})
    print("private providers only:", llm.openrouter_privacy())
    meter = CostMeter(budget=0.05)
    switched = []
    ctx = CallContext(meter=meter, chat_id="t", run_id="r", on_switch=lambda a, b: switched.append((a, b)))
    for model, thinking in MODELS:
        chunks = []
        try:
            r = await llm.complete(model, [{"role": "user", "content": "In one short sentence: what is a token?"}], stage="test", ctx=ctx,
                                   stream=True, thinking=thinking, max_tokens=300, on_text=lambda t: chunks.append(t), allow_fallback=False)
            print(f"{model:36s} think={thinking:4s} chunks={len(chunks):3d} in={r.usage.prompt} out={r.usage.completion} "
                  f"reasoning={r.usage.reasoning} cost=${r.usage.cost:.6f} | {r.text.strip()[:60]!r}")
        except llm.LLMError as e:
            print(f"{model:36s} think={thinking:4s} FAILED: {e}")
    r = await llm.complete("does-not/exist", [{"role": "user", "content": "say ok"}], stage="test", ctx=ctx, max_tokens=5)
    print("fallback ->", r.model, "| switched:", switched[:1])
    print("meter:", meter.snapshot())
    nim = registry.get("nim:nvidia/llama-3.1-nemotron-70b-instruct")
    print("nim available?", nim.available, nim.why_unavailable)
    await llm.close_client()


asyncio.run(main())
