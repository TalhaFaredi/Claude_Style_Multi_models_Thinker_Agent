"""Chat export and import (spec Part 2 section 8).

The .zip holds everything the chat knows, so an import restores it without paying to read files again:
  manifest.json   format version, app version, date, models used, SHA-256 of every part
  messages.jsonl  every message word for word
  ledger.json, summaries.json, facts.json
  files/ (optional originals)   readings/ (saved readings, Document Cards, fingerprints)
  transcript.md   a plain copy for people

Import: check the version and every checksum (refuse and name the broken part, C43); treat everything as
DATA (C44): roles are limited to user/assistant/sys, so an imported line can never become a system prompt;
every id is validated before it touches the database or the disk; readings are reused at $0.
"""
from __future__ import annotations

import hashlib
import asyncio
import base64
import math
import io
import json
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from app import files
from app.core import db, config
from app.core.config import APP_VERSION, EXPORT_FORMAT_VERSION, PARSE_VERSION
from app.core.privacy import is_fingerprint
from app.memory.archive import create_chat, get_chat
from app.memory.facts import add_fact
from app.memory.ledger import KINDS
from app.memory.settings import get_settings
from app.core.tokens import estimate_tokens


def _zip_type(password):
    if password:
        import pyzipper
        return pyzipper.AESZipFile
    return zipfile.ZipFile


class ExportError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _dump(rows) -> bytes:
    return json.dumps([dict(r) for r in rows], ensure_ascii=False).encode("utf-8")


def _export_facts(chat_id: str):
    chosen = {r["id"]: dict(r) for r in db.q("SELECT DISTINCT f.* FROM facts f LEFT JOIN chat_facts cf ON cf.fact_id=f.id WHERE (f.chat_id=? OR cf.chat_id=?) AND f.deleted=0 AND f.user_id=?", (chat_id, chat_id, db.uid()))}
    all_facts = [dict(r) for r in db.q("SELECT * FROM facts WHERE deleted=0 AND user_id=?", (db.uid(),))]
    while True:
        ids = set(chosen)
        for fact in all_facts:
            if fact["replaced_by"] in ids or any(f.get("replaced_by") == fact["id"] for f in chosen.values()):
                chosen[fact["id"]] = fact
        if ids == set(chosen):
            return list(chosen.values())


def build_export(chat_id: str, include_files: bool = False, password: str | None = None) -> bytes:
    chat = get_chat(chat_id)
    if not chat:
        raise ExportError("Unknown chat", 404)
    rows = db.q("SELECT * FROM messages WHERE chat_id=? ORDER BY seq", (chat_id,))
    parts: dict[str, bytes] = {
        "messages.jsonl": "\n".join(json.dumps({**{k: r[k] for k in r.keys() if k not in ("chat_id", "origin_id")}, "id": r["origin_id"] or r["id"]}, ensure_ascii=False) for r in rows).encode("utf-8"),
        "ledger.json": _dump(db.q("SELECT num,kind,text,src_seq,status,ts FROM ledger WHERE chat_id=? ORDER BY num", (chat_id,))),
        "summaries.json": _dump(db.q("SELECT id,from_seq,to_seq,text,seqs,tokens,ts,merged_into FROM summaries WHERE chat_id=? ORDER BY id", (chat_id,))),
        "facts.json": _dump(_export_facts(chat_id)),
        "files.json": _dump(db.q("SELECT f.fingerprint,f.name,f.size,f.mime,f.pages,f.kinds,f.created,fc.reader FROM files f JOIN file_chats fc ON fc.fingerprint=f.fingerprint WHERE fc.chat_id=?", (chat_id,))),
    }
    transcript = [f"# {chat['title']}", ""] + [f"**{r['role']}** ({datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d %H:%M')}):\n\n{r['content']}\n"
                                               for r in rows if r["role"] in ("user", "assistant")]
    parts["transcript.md"] = "\n".join(transcript).encode("utf-8")
    for r in db.q("SELECT fingerprint FROM file_chats WHERE chat_id=?", (chat_id,)):
        fp = r["fingerprint"]
        f = db.one("SELECT * FROM files WHERE fingerprint=?", (fp,))
        if not f:
            continue
        for rd in db.q("SELECT * FROM readings WHERE fingerprint=? AND version=?", (fp, PARSE_VERSION)):
            pages = []
            for pg in json.loads(rd["pages"]):
                pg = dict(pg)
                image = pg.pop("image", None)
                if image and Path(image).is_file():
                    member = f"images/{fp}/{pg['page']}{Path(image).suffix}"
                    parts[member] = Path(image).read_bytes()
                    pg["imagePart"] = member
                pages.append(pg)
            parts[f"readings/{fp}.{rd['reader']}.json"] = json.dumps({
                "fingerprint": fp, "name": f["name"], "size": f["size"], "reader": rd["reader"], "version": rd["version"],
                "pages": pages,
                "vectors": [{"idx": ch["idx"], "model": ch["embedding_model"], "vector": base64.b64encode(ch["embedding"]).decode()}
                            for ch in db.q("SELECT idx,embedding,embedding_model FROM chunks WHERE fingerprint=? AND reader=? AND embedding IS NOT NULL", (fp,rd["reader"]))],
                "card": json.loads(rd["card"] or "{}"), "cost": rd["cost"], "analysis": json.loads(f["kinds"])}, ensure_ascii=False).encode("utf-8")
        if include_files and f["path"] and Path(f["path"]).is_file():
            parts[f"files/{fp}{Path(f['name']).suffix.lower()}"] = Path(f["path"]).read_bytes()
    manifest = {"formatVersion": EXPORT_FORMAT_VERSION, "appVersion": APP_VERSION, "date": datetime.now().isoformat(timespec="seconds"),
                "chat": {"title": chat["title"], "temp": bool(chat["temp"])}, "modelsUsed": sorted({r["model"] for r in rows if r["model"]}), "includesOriginalFiles": include_files,
                "embeddingModel": config.EMBED_MODEL,
                "checksums": {name: _sha(b) for name, b in parts.items()}}
    buf = io.BytesIO()
    with _zip_type(password)(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if password:
            import pyzipper
            z.setpassword(password.encode())
            z.setencryption(pyzipper.WZ_AES, nbits=256)
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, b in parts.items():
            z.writestr(name, b)
    return buf.getvalue()


def _open_checked(data: bytes, password: str | None = None) -> tuple[zipfile.ZipFile, dict, set[str]]:
    """C43: the format version and every checksum must match, or the import is refused naming the part."""
    try:
        z = _zip_type(password)(io.BytesIO(data))
        if password:
            z.setpassword(password.encode())
    except zipfile.BadZipFile:
        raise ExportError("This is not a valid .zip file.", 422)
    names = set(z.namelist())
    if len(names) != len(z.infolist()) or len(names) > 10000 or sum(i.file_size for i in z.infolist()) > 500 * 1024 * 1024:
        raise ExportError("The archive has duplicate parts or expands beyond the 500 MB / 10,000-part limit.", 413)
    if any(Path(n).is_absolute() or '..' in Path(n).parts or '\\' in n for n in names):
        raise ExportError("The archive contains an unsafe part name.", 422)
    if "manifest.json" not in names:
        raise ExportError("Broken part: manifest.json is missing.", 422)
    try:
        manifest = json.loads(z.read("manifest.json"))
    except (RuntimeError, NotImplementedError):
        raise ExportError("This archive needs its correct password.", 422)
    except ValueError:
        raise ExportError("Broken part: manifest.json is not valid.", 422)
    if not isinstance(manifest, dict) or manifest.get("formatVersion") != EXPORT_FORMAT_VERSION:
        raise ExportError(f"Unsupported format version in manifest.json; this app reads version {EXPORT_FORMAT_VERSION}.", 422)
    sums = manifest.get("checksums")
    if not isinstance(sums, dict):
        raise ExportError("Broken part: manifest.json checksums are missing.", 422)
    for name in {"messages.jsonl", "ledger.json", "summaries.json", "facts.json"} - names:
        raise ExportError(f"Broken part: {name} is missing.", 422)
    for name, expected in sums.items():
        if name not in names:
            raise ExportError(f"Broken part: {name} is missing.", 422)
        if _sha(z.read(name)) != expected:
            raise ExportError(f"Broken part: {name} does not match its checksum.", 422)
    for name in sorted(names - set(sums) - {"manifest.json"}):
        raise ExportError(f"Broken part: {name} is not listed in the manifest.", 422)
    return z, manifest, names


def _json(z: zipfile.ZipFile, names: set[str], name: str) -> list:
    if name not in names:
        return []
    try:
        data = json.loads(z.read(name))
    except ValueError:
        raise ExportError(f"Broken part: {name} is not valid JSON.", 422)
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        raise ExportError(f"Broken part: {name} is not a list of records.", 422)
    return data


def _validate_number(value, integer=False):
    n = float(value or 0)
    if not math.isfinite(n) or n < 0 or (integer and n != int(n)):
        raise ValueError("a number is negative, nonfinite or not an integer")
    return n


async def import_chat(data: bytes, password: str | None = None) -> dict:
    z, manifest, names = _open_checked(data, password)
    # Validate all structured parts before creating a chat; a failed import leaves no partial chat.
    try:
        for name in ("ledger.json", "summaries.json", "facts.json", "files.json"):
            for record in _json(z, names, name):
                for key in ("ts", "cost", "created", "replaced_at"):
                    if key in record and record[key] is not None:
                        _validate_number(record[key])
                for key in ("id", "num", "from_seq", "to_seq", "size", "pages", "src_seq", "replaced_by", "tokens"):
                    if key in record and record[key] is not None:
                        _validate_number(record[key], integer=True)
                if name in ("ledger.json", "summaries.json", "facts.json") and not isinstance(record.get("text", ""), str):
                    raise ValueError(f"invalid text in {name}")
                if name == "summaries.json":
                    seqs = record.get("seqs") or "[]"
                    seqs = json.loads(seqs) if isinstance(seqs, str) else seqs
                    if not isinstance(seqs, list) or not all(isinstance(n, int) and n >= 0 for n in seqs):
                        raise ValueError("invalid summary message links")
                if name == "files.json":
                    if not is_fingerprint(str(record.get("fingerprint", ""))) or record.get("reader") not in (*files.READER_IDS, None):
                        raise ValueError("invalid file fingerprint or reader")
                    kinds = record.get("kinds") or '{"pages":[]}'
                    kinds = json.loads(kinds) if isinstance(kinds, str) else kinds
                    if not isinstance(kinds, dict) or not isinstance(kinds.get("pages"), list):
                        raise ValueError("invalid page metadata")
        for line in z.read("messages.jsonl").decode().splitlines():
            if line.strip():
                message = json.loads(line)
                if not isinstance(message, dict) or not isinstance(message.get("content", ""), str):
                    raise ValueError("message is not a record with text content")
                for key in ("ts", "cost"):
                    _validate_number(message.get(key))
                _validate_number(message.get("seq"), integer=True)
        for name in (n for n in names if n.startswith("readings/")):
            value = json.loads(z.read(name))
            if not isinstance(value, dict) or not is_fingerprint(str(value.get("fingerprint", ""))) or value.get("reader") not in files.READER_IDS or not isinstance(value.get("pages"), list):
                raise ValueError(f"invalid reading {name}")
            _validate_number(value.get("cost"))
            _validate_number(value.get("version"), integer=True)
            for pg in value["pages"]:
                if not isinstance(pg, dict) or int(pg.get("page", 0)) < 1 or not isinstance(pg.get("text", ""), str):
                    raise ValueError(f"invalid page in {name}")
                if pg.get("imagePart") and (pg["imagePart"] not in names or not pg["imagePart"].startswith(f"images/{value['fingerprint']}/")):
                    raise ValueError(f"missing image in {name}")
        for name in (n for n in names if n.startswith("files/")):
            if _sha(z.read(name)) != Path(name).name[:64]:
                raise ValueError(f"fingerprint mismatch in {name}")
    except (ValueError, TypeError, KeyError, UnicodeError) as e:
        raise ExportError(f"Broken part: {e}", 422)
    warnings: list[str] = []
    cid = uuid.uuid4().hex[:12]
    title = str((manifest.get("chat") or {}).get("title") or "Imported chat")[:60]
    create_chat(f"{title} (imported)", temp=bool((manifest.get("chat") or {}).get("temp")), chat_id=cid)

    sums_rows = [s for s in _json(z, names, "summaries.json") if isinstance(s, dict) and isinstance(s.get("id"), int)]
    sum_map: dict[int, int] = {}
    for s in sorted(sums_rows, key=lambda x: x["id"]):
        sum_map[s["id"]] = db.run("INSERT INTO summaries(chat_id,from_seq,to_seq,text,seqs,tokens,ts,merged_into) VALUES(?,?,?,?,?,?,?,NULL)",
                                  (cid, int(s.get("from_seq") or 0), int(s.get("to_seq") or 0), str(s.get("text", "")), str(s.get("seqs") or "[]"),
                                   estimate_tokens(str(s.get("text", ""))), float(s.get("ts") or db.now())))
    for s in sums_rows:
        if s.get("merged_into") in sum_map:
            db.run("UPDATE summaries SET merged_into=? WHERE id=?", (sum_map[s["merged_into"]], sum_map[s["id"]]))

    n_msgs = 0
    for line in z.read("messages.jsonl").decode("utf-8").splitlines() if "messages.jsonl" in names else []:
        if not line.strip():
            continue
        try:
            m = json.loads(line)
        except ValueError:
            raise ExportError("Broken part: messages.jsonl has a line that is not valid JSON.", 422)
        role = m.get("role") if m.get("role") in ("user", "assistant", "sys") else "user"   # C44: never "system"
        content = str(m.get("content", ""))
        meta = m.get("meta") if isinstance(m.get("meta"), str) else None
        original_id = str(m.get("id") or uuid.uuid4().hex[:16])
        mid = original_id if not db.one("SELECT 1 FROM messages WHERE id=?", (original_id,)) else uuid.uuid4().hex[:16]
        with db.tx() as c:
            c.execute("INSERT INTO messages(id,chat_id,seq,role,content,ts,model,tokens,cost,meta,pinned,summarized_into,imported) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)",
                      (mid, cid, int(m.get("seq") or n_msgs + 1), role, content, float(m.get("ts") or db.now()), str(m.get("model") or "") or None,
                       estimate_tokens(content), float(m.get("cost") or 0.0), meta, 1 if m.get("pinned") else 0, sum_map.get(m.get("summarized_into"))))
            if role in ("user", "assistant"):
                c.execute("INSERT INTO msg_fts(content,chat_id,msg_id) VALUES(?,?,?)", (content, cid, mid))
            c.execute("UPDATE messages SET origin_id=? WHERE id=?", (original_id, mid))
        n_msgs += 1

    n_led = 0
    for it in _json(z, names, "ledger.json"):
        if isinstance(it, dict) and str(it.get("text") or "").strip():
            db.run("INSERT INTO ledger(chat_id,num,kind,text,src_seq,status,ts) VALUES(?,?,?,?,?,?,?)",
                   (cid, int(it.get("num") or n_led + 1), it.get("kind") if it.get("kind") in KINDS else "decision", str(it["text"]),
                    it.get("src_seq") if isinstance(it.get("src_seq"), int) else None,
                    it.get("status") if it.get("status") in ("open", "changed", "closed") else "open", float(it.get("ts") or db.now())))
            n_led += 1

    n_facts = 0
    fact_map = {}
    if get_settings()["longMemory"] and not (manifest.get("chat") or {}).get("temp"):
        for f in _json(z, names, "facts.json"):
            if isinstance(f, dict) and str(f.get("text") or "").strip():
                text, source, ts = str(f["text"]), str(f.get("source") or "imported chat"), float(f.get("ts") or db.now())
                existing = db.one("SELECT id FROM facts WHERE text=? AND source=? AND ts=? AND deleted=0 AND user_id=?", (text, source, ts, db.uid()))
                fid = existing["id"] if existing else add_fact(text, source, cid, ts=ts)
                fact_map[f.get("id", n_facts)] = fid
                db.run("INSERT OR IGNORE INTO chat_facts(chat_id,fact_id) VALUES(?,?)", (cid, fid))
                n_facts += 1
        for f in _json(z, names, "facts.json"):
            if f.get("id") in fact_map and f.get("replaced_by") in fact_map:
                db.run("UPDATE facts SET replaced_by=?,replaced_at=? WHERE id=?", (fact_map[f["replaced_by"]], f.get("replaced_at"), fact_map[f["id"]]))

    seen: set[str] = set()
    multi = config.AUTH_REQUIRED
    if multi:
        # Readings are cached by file fingerprint and shared between accounts. Trusting fingerprints, file records or
        # readings from an uploaded archive would let one user plant fake text for a file another user uploads later.
        # So only original files are taken (re-checked and analysed like any upload) and readings are rebuilt on demand.
        for f in _json(z, names, "files.json"):
            fp = str(f.get("fingerprint", ""))
            file_name = Path(str(f.get("name") or "file")).name[:200]
            original = next((n for n in names if n.startswith(f"files/{fp}")), None) if is_fingerprint(fp) else None
            if original is None:
                warnings.append(f"{file_name} was not included in the archive. Attach it again to read it.")
                continue
            try:
                await asyncio.to_thread(files.ingest, cid, file_name, z.read(original))
                seen.add(fp)
            except files.FileError as e:
                warnings.append(f"{file_name} was skipped: {e}")
    selected_readers = {f["fingerprint"]: f.get("reader") for f in _json(z, names, "files.json") if is_fingerprint(str(f.get("fingerprint", "")))}
    for f in ([] if multi else _json(z, names, "files.json")):
        fp = str(f.get("fingerprint", ""))
        if not is_fingerprint(fp):
            continue
        file_name = Path(str(f.get("name") or "file")).name[:200]
        if not db.one("SELECT 1 FROM files WHERE fingerprint=?", (fp,)):
            original = next((n for n in names if n.startswith(f"files/{fp}")), None)
            path = str(files.store_original(fp, file_name, z.read(original))) if original else ""
            kinds = f.get("kinds") or '{"pages":[]}'
            db.run("INSERT INTO files(fingerprint,name,size,mime,pages,kinds,path,created) VALUES(?,?,?,?,?,?,?,?)",
                   (fp, file_name, int(f.get("size") or 0), str(f.get("mime") or ""), int(f.get("pages") or 0), kinds if isinstance(kinds,str) else json.dumps(kinds), path, float(f.get("created") or db.now())))
        files.link(cid, fp, f.get("reader"))
        seen.add(fp)
    for name in sorted(n for n in names if n.startswith("readings/") and not multi):
        rd = json.loads(z.read(name))
        fp, reader = str(rd.get("fingerprint", "")), str(rd.get("reader", ""))
        if not is_fingerprint(fp) or reader not in files.READER_IDS or not isinstance(rd.get("pages"), list):
            warnings.append(f"{name} has an invalid file id or reader; skipped.")
            continue
        file_name = Path(str(rd.get("name") or "file")).name[:200]
        if db.one("SELECT 1 FROM files WHERE fingerprint=?", (fp,)) is None:
            path = ""
            orig = next((n for n in names if n.startswith(f"files/{fp}")), None)
            if orig:
                b = z.read(orig)
                if files.fingerprint(b) == fp:
                    path = str(files.store_original(fp, file_name, b))
                else:
                    warnings.append(f"{orig} does not match its fingerprint; original skipped.")
            db.run("INSERT INTO files(fingerprint,name,size,mime,pages,kinds,path,created) VALUES(?,?,?,?,?,?,?,?)",
                   (fp, file_name, int(rd.get("size") or 0), "", len(rd["pages"]), json.dumps(rd.get("analysis") or {"pages": []}), path, db.now()))
        files.link(cid, fp, selected_readers.get(fp) or reader)
        version = int(rd.get("version") or PARSE_VERSION)
        pages = [{**p, "image": None} for p in rd["pages"] if isinstance(p, dict)]
        for pg in pages:
            if pg.get("imagePart"):
                from app.files.store import PAGES_DIR
                target = PAGES_DIR / fp[:16] / f"{pg['page']}{Path(pg['imagePart']).suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(pg.pop("imagePart")))
                pg["image"] = str(target)
        if db.one("SELECT 1 FROM readings WHERE fingerprint=? AND reader=? AND version=?", (fp, reader, version)) is None:
            db.run("INSERT INTO readings(fingerprint,reader,version,pages,card,cost,ts) VALUES(?,?,?,?,?,?,?)",
                   (fp, reader, version, json.dumps(pages), json.dumps(rd.get("card") or {}), float(rd.get("cost") or 0.0), db.now()))
        if db.one("SELECT 1 FROM chunks WHERE fingerprint=? AND reader=? LIMIT 1", (fp, reader)) is None:
            await files.index_chunks(fp, reader, file_name, [{"page": p.get("page", 1), "kind": p.get("kind", "text"), "table": bool(p.get("table")),
                                                              "text": str(p.get("text") or "")} for p in pages], paid_embeddings=False)
            for vector in rd.get("vectors", []):
                try:
                    blob = base64.b64decode(vector["vector"], validate=True)
                    db.run("UPDATE chunks SET embedding=?,embedding_model=? WHERE fingerprint=? AND reader=? AND idx=?",
                           (blob, vector.get("model"), fp, reader, int(vector["idx"])))
                except (KeyError, ValueError, TypeError):
                    warnings.append("An optional saved embedding could not be restored; keyword search remains available.")
        seen.add(fp)
    if n_msgs:
        warnings.append("Everything is loaded word for word. If the window is too small for it, the next message compacts older turns safely.")
    reindex = manifest.get("embeddingModel") not in (None, config.EMBED_MODEL)
    if reindex:
        warnings.append("The embedding model changed. Keyword indexes are ready; paid meaning reindexing needs a new cost approval.")
    reindex_files = []
    if reindex:
        for fp in sorted(seen):
            try:
                estimate = files.reindex_estimate(cid, fp)
                if estimate["chunks"]:
                    row = db.one("SELECT name FROM files WHERE fingerprint=?", (fp,))
                    reindex_files.append({**estimate, "name": row["name"] if row else "File"})
            except files.FileError:
                pass
    return {"chatId": cid, "title": title, "messages": n_msgs, "files": len(seen), "filesReused": len(seen), "filesReread": 0,
            "facts": n_facts, "ledger": n_led, "summaries": len(sums_rows), "readingCostUsd": 0.0,
            "reindexApprovalRequired": bool(reindex_files), "reindexFiles": reindex_files, "warnings": warnings}
