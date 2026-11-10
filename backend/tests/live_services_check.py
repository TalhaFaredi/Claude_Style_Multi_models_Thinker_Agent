"""Manual live check of the web tools and embeddings (embeddings cost a millionth of a dollar).
Run: .venv/Scripts/python.exe -m tests.live_services_check"""
import asyncio
import os
from pathlib import Path

os.environ.setdefault("DATA_DIR", str(Path(__file__).resolve().parents[1] / "data_test"))

from app import llm, tools  # noqa: E402
from app.core import config, db  # noqa: E402
from app.files.search import embed_texts  # noqa: E402
from app.tools import ToolRun  # noqa: E402


async def main():
    db.reset_for_tests()
    state = ToolRun(chat_id="live", allowed_tools={"web_search", "read_webpage", "calculator"})
    r = await tools.execute("web_search", {"query": "solar power capacity 2025"}, state)
    print("web_search:", r.ok, r.done_label, r.citations[:3])
    if state.allowed_urls:
        url = next(iter(state.allowed_urls))
        p = await tools.execute("read_webpage", {"url": url}, state)
        print("read_webpage:", p.ok, p.done_label, len(p.text), "chars")
    blocked = await tools.execute("read_webpage", {"url": "https://example.com/?leak=secret"}, state)
    print("read_webpage on a link not from search:", blocked.ok, blocked.done_label)
    print("calculator:", (await tools.execute("calculator", {"expression": "48250*1.07/12"}, state)).text)
    vecs = await embed_texts(["car price", "vehicle cost"])
    print("embeddings:", config.EMBED_MODEL, "->", (len(vecs), len(vecs[0])) if vecs else "unavailable (keyword search only)")
    await llm.close_client()


asyncio.run(main())
