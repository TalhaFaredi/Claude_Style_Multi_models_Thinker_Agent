"""Live check 3: context meter, AUTO-COMPACTION with planted facts, ledger, long-term memory, files, export/import.
Run from backend/: python -m tests.live_3_memory   (spends well under 1 cent)"""
import io
import json
import zipfile

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .api_client import BAL, BASE, FAST, client, payload, stream, summarize

PLANTED = ["48,250", "2026-03-14", "dana@falcon-labs.org", "Dana Whitfield"]


def make_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    facts = {1: "The Zephyr turbine maintenance manual. Rotor blades must be inspected every 400 operating hours.",
             3: "Lubrication: use grade ISO VG 320 gear oil. The gearbox holds 38 liters of oil.",
             5: "Safety: lock out the turbine before climbing the tower. The maximum wind speed for climbing is 12 meters per second.",
             7: "Warranty: the Zephyr turbine warranty lasts 9 years from the commissioning date."}
    for page in range(1, 9):
        c.setFont("Helvetica", 11)
        y = 800
        c.drawString(60, y, facts.get(page, f"Appendix page {page}. General notes about site logistics and paperwork.")); y -= 24
        for i in range(25):
            c.drawString(60, y, f"Reference line {i} on page {page}: routine procedure text for the Zephyr turbine crew."); y -= 18
        if page == 4:
            y -= 10
            for row in ["Part | Interval | Cost", "Blade | 400 h | 1200", "Gearbox | 2000 h | 5400", "Brake | 800 h | 650"]:
                c.drawString(60, y, row); y -= 18
        c.showPage()
    c.save()
    return buf.getvalue()


def show(label, s):
    print(f"{label}: done={s['done']} cost={s['cost']['usd'] if s['cost'] else None} errors={s['errors']} warnings={s['warnings']}")


with client() as c:
    # use a small working window so the 70/85/95% levels are reachable cheaply
    c.put(f"{BASE}/api/settings", json={"windowCap": 4000, "autoCompact": True, "longMemory": True})
    chat = c.post(f"{BASE}/api/chats", json={}).json()["id"]

    s = summarize(stream(c, payload(chat, "My name is Dana Whitfield. The Falcon project budget is $48,250 and the deadline is 2026-03-14. "
                                          "Our contact is dana@falcon-labs.org. Please remember this.")))
    show("planted facts", s)

    compacted_at = None
    levels = []
    topics = ["photosynthesis", "the French revolution", "how vaccines work", "black holes", "the water cycle", "plate tectonics", "the printing press", "how batteries work", "the Roman empire", "volcanoes"]
    topics = (topics * 4)[:36]
    for i, topic in enumerate(topics):
        if compacted_at is not None and i > compacted_at + 1:
            break
        ev = stream(c, payload(chat, f"Explain {topic} in about 120 words.", simple={"model": FAST, "thinking": "off", "style": "balanced", "tools": {}}))
        s = summarize(ev)
        pct = s["context"]["percent"] if s["context"] else None
        levels.append((topic[:12], pct, s["context"]["level"] if s["context"] else None))
        comp = [e for e in ev if e["type"] == "compact"]
        if comp:
            compacted_at = i
            print(f"\n*** AUTO-COMPACTION during turn {i}: steps {[e['step'] for e in comp]} | note: {[e['text'] for e in ev if e['type'] == 'note']}")
            print(f"    context after: {s['context']['percent']}% ({s['context']['level']})")
    print("window fill per turn:", levels)
    print("compacted:", compacted_at is not None)

    led = c.get(f"{BASE}/api/chats/{chat}/ledger").json()
    print("\nledger:", [(x["num"], x["kind"], x["text"][:70]) for x in led["ledger"]][:8])
    print("summaries:", [(s["from_seq"], s["to_seq"], len(s["text"])) for s in led["summaries"]])
    all_text = " ".join(x["text"] for x in led["ledger"]) + " " + " ".join(s["text"] for s in led["summaries"])
    print("planted facts survive in ledger+summary:", {p: (p in all_text) for p in PLANTED})
    got = c.get(f"{BASE}/api/chats/{chat}", params={"model": FAST}).json()
    print("archive keeps every message:", len([m for m in got["messages"] if m["role"] in ("user", "ai")]), "messages;",
          "summarized flags:", sum(1 for m in got["messages"] if m.get("summarized")))

    s = summarize(stream(c, payload(chat, "What is the Falcon project budget, the deadline, and the contact email? Also what is my name?",
                                    simple={"model": FAST, "thinking": "off", "style": "precise", "tools": {}})))
    print("\nAFTER COMPACTION ->", s["text"][:300].replace("\n", " "))
    print("recalled:", {p: (p.lower() in s["text"].lower()) for p in PLANTED})

    mem = c.get(f"{BASE}/api/memory").json()
    print("\nlong-term facts:", [f["text"][:70] for f in mem["facts"]][:4])
    s = summarize(stream(c, payload(chat, "Update: my Falcon project budget is now $60,000.", simple={"model": FAST, "thinking": "off", "style": "balanced", "tools": {}})))
    import time; time.sleep(6)   # memory writer runs after the reply
    hist = c.get(f"{BASE}/api/memory", params={"history": True}).json()["facts"]
    print("facts incl. history:", [(f["text"][:50], "REPLACED " + str(f["replacedOn"]) if f["replaced"] else "current") for f in hist][:5])

    # ---------------- files
    chat2 = c.post(f"{BASE}/api/chats", json={}).json()["id"]
    pdf = make_pdf()
    up = c.post(f"{BASE}/api/chats/{chat2}/files", files={"file": ("zephyr_manual.pdf", pdf, "application/pdf")}).json()
    fp = up["fingerprint"]
    print("\n[file] upload:", up["name"], up["pages"], "pages | kinds:", up["kinds"], "| auto plan total:", up["plans"]["auto"]["total"], "| readers:", {k: v["available"] for k, v in up["readers"].items()})
    rd = c.post(f"{BASE}/api/files/{fp}/read", json={"chatId": chat2, "reader": "auto"}).json()
    print("[file] read: reused", rd["reused"], "cost", rd["cost"], "| card:", {k: (v if k != "summary" else v[:80]) for k, v in rd["card"].items() if k in ("title", "pages", "summary", "tables")})
    rd2 = c.post(f"{BASE}/api/files/{fp}/read", json={"chatId": chat2, "reader": "auto"}).json()
    print("[file] read again (Parse Cache):", "reused", rd2["reused"], "cost", rd2["cost"])
    s = summarize(stream(c, payload(chat2, "How many liters of oil does the gearbox hold, and what is the climbing wind limit? Cite pages.",
                                    simple={"model": BAL, "thinking": "off", "style": "precise", "tools": {"files": True}})))
    print("[file] answer:", s["text"][:260].replace("\n", " "))
    print("[file] statuses:", s["statuses"][:4], "| citations:", [e["items"] for e in []])
    # force SEARCH mode: shrink the window so the file no longer fits its 35% budget
    c.put(f"{BASE}/api/settings", json={"windowCap": 4000})
    s = summarize(stream(c, payload(chat2, "What is the warranty period of the Zephyr turbine?", simple={"model": FAST, "thinking": "off", "style": "precise", "tools": {"files": True}})))
    print("[file/search-mode] statuses:", s["statuses"][:3], "| answer:", s["text"][:200].replace("\n", " "))

    # ---------------- export / import
    z = c.get(f"{BASE}/api/chats/{chat2}/export", params={"includeFiles": True})
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    print("\n[export]", z.status_code, "parts:", zf.namelist())
    imp = c.post(f"{BASE}/api/import", files={"file": ("chat.zip", z.content, "application/zip")}).json()
    print("[import] report:", {k: v for k, v in imp.items() if k != "warnings"})
    # tamper
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as nz:
        for n in zf.namelist():
            data = zf.read(n)
            if n == "messages.jsonl":
                data = data.replace(b"zephyr", b"ZEPHYR", 1) if b"zephyr" in data else data + b" "
            nz.writestr(n, data)
    bad = c.post(f"{BASE}/api/import", files={"file": ("bad.zip", buf.getvalue(), "application/zip")})
    print("[import tampered]", bad.status_code, bad.json())
    pw = c.get(f"{BASE}/api/chats/{chat2}/export", params={"password": "x"})
    print("[export password]", pw.status_code, pw.json())
    c.put(f"{BASE}/api/settings", json={"windowCap": 32000})
