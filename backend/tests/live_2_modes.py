"""Live check 2: web tool, Thinker (agents + composer), Planner (approval gate + PDF). python -m tests.live_2_modes"""
import threading
import time

import httpx

from .api_client import BAL, BASE, FAST, client, payload, stream, summarize

with client() as c:
    chat = c.post(f"{BASE}/api/chats", json={}).json()["id"]

    # ---- web tool
    p = payload(chat, "Search the web: what is the latest stable version of Python released? Cite your source.")
    p["simple"]["tools"]["web"] = True
    ev = stream(c, p)
    s = summarize(ev)
    print("[web] tool events:", [(e["state"], e["label"]) for e in ev if e["type"] == "tool"])
    print("[web] citations:", [e["items"] for e in ev if e["type"] == "citations"], "| cost:", s["cost"], "| errors:", s["errors"])
    print("[web] answer:", s["text"][:260].replace("\n", " "))

    # ---- Thinker, same model, 3 roles, on their own
    t0 = time.time()
    ev = stream(c, payload(chat, "Should a small startup use one strong model or several cheap ones for its support bot?", mode="thinker"))
    s = summarize(ev)
    agent_evs = [e for e in ev if e["type"] == "agents"]
    print(f"\n[thinker] {time.time()-t0:.0f}s done={s['done']} types={s['types']}")
    print("[thinker] roles:", [a["role"] for a in agent_evs[-1]["agents"]] if agent_evs else None)
    print("[thinker] rounds:", [e["roundText"] for e in agent_evs][:6])
    print("[thinker] cost:", s["cost"], "| warnings:", s["warnings"], "| errors:", s["errors"])
    print("[thinker] answer:", s["text"][:300].replace("\n", " "))

    # ---- Thinker, different models, together (debate), 2 rounds
    p = payload(chat, "Is it better to learn Python or JavaScript first? Give a clear recommendation.", mode="thinker",
                team={"source": "mixed", "model": FAST, "agents": 3, "mixed": [FAST, "mistralai/mistral-nemo", "google/gemma-3-12b-it"], "style": "together", "rounds": 2, "composer": "auto"})
    ev = stream(c, p)
    s = summarize(ev)
    print("\n[debate] rounds:", [e["roundText"] for e in ev if e["type"] == "agents"][:10])
    print("[debate] cost:", s["cost"], "| warnings:", s["warnings"], "| errors:", s["errors"], "| answer:", s["text"][:200].replace("\n", " "))

    # ---- Planner: must stop at the approval gate; approve from a second thread
    p = payload(chat, "Make a 1-page PDF report on why sleep matters for students", mode="planner")
    p["simple"]["model"] = BAL
    events: list[dict] = []
    approved = threading.Event()

    def on_event(e):
        events.append(e)
        if e["type"] == "plan" and e["awaitingApproval"] and not approved.is_set():
            approved.set()
            running_before = [s for s in e["steps"] if s["status"] in ("running", "checking", "done")]
            print("[planner] plan shown, steps:", [(s["task"][:40], s["modeLabel"]) for s in e["steps"]], "| est:", e.get("estimateUsd"), "| already running:", running_before)
            time.sleep(1.0)   # nothing must happen while we wait
            n_before = len(events)
            time.sleep(2.0)
            print("[planner] events while waiting for approval:", len(events) - n_before)
            httpx.post(f"{BASE}/api/runs/{p['id']}/approve", timeout=30)

    ev = stream(c, p, on_event=on_event, timeout=400)
    s = summarize(ev)
    plans = [e for e in ev if e["type"] == "plan"]
    print("[planner] phases:", [pl["phase"] for pl in plans][:3], "...", plans[-1]["phase"])
    print("[planner] final steps:", [(st["status"], st["task"][:30], st.get("note")) for st in plans[-1]["steps"]])
    out = [e for e in ev if e["type"] == "output"]
    print("[planner] output:", out[-1]["file"] if out else None, "| cost:", s["cost"], "| warnings:", s["warnings"], "| errors:", s["errors"])
    if out:
        r = c.get(f"{BASE}/api/artifacts/{out[-1]['file']['id']}")
        print("[planner] download:", r.status_code, r.headers.get("content-type"), len(r.content), "bytes", r.content[:5])
