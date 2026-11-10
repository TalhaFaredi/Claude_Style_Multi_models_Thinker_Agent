"""Live check 1: Simple mode, tools, routing, cost, context, persistence. Run from backend/: python -m tests.live_1_simple"""
from .api_client import BAL, BASE, client, payload, stream, summarize

with client() as c:
    cfg = c.get(f"{BASE}/api/config").json()
    print("providers:", {k: (v["ok"], v.get("reason")) for k, v in cfg["providers"].items()})
    chat = c.post(f"{BASE}/api/chats", json={}).json()["id"]
    print("chat:", chat)

    # 1. Auto -> simple, with web search
    p = payload(chat, "What is the capital of Australia, and what is its population?", mode="auto")
    p["simple"]["tools"]["web"] = True
    ev = stream(c, p)
    s = summarize(ev)
    print("\n[auto/simple+web] done:", s["done"], "| types:", s["types"])
    print("route:", [e for e in ev if e["type"] == "route"])
    print("statuses:", s["statuses"])
    print("tool events:", [e for e in ev if e["type"] == "tool"])
    print("citations:", [e["items"] for e in ev if e["type"] == "citations"])
    print("cost:", s["cost"], "| warnings:", s["warnings"], "| errors:", s["errors"])
    print("context:", {k: s["context"][k] for k in ("percent", "level", "usedTokens", "usableTokens")} if s["context"] else None)
    print("answer:", s["text"][:300].replace("\n", " "))

    # 2. follow-up uses memory of the chat
    ev = stream(c, payload(chat, "And what was the first thing I asked you about?"))
    s = summarize(ev)
    print("\n[follow-up] answer:", s["text"][:200].replace("\n", " "), "| cost:", s["cost"])

    # 3. persistence
    got = c.get(f"{BASE}/api/chats/{chat}", params={"model": BAL}).json()
    print("\n[reload] messages:", [(m["role"], (m.get("text") or "")[:30]) for m in got["messages"]])
    print("[reload] chat cost:", got["costUsd"], "| title:", got["chat"]["title"])
    u = c.get(f"{BASE}/api/usage").json()
    print("[usage] month total:", u["totalUsd"], "| by stage:", [(x["stage"], x["cost"]) for x in u["byStage"]])
