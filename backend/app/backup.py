"""Consistent backups of the live database (safe while the server is running: SQLite's online backup API).

    python -m app.backup                      # one backup now, keep the newest 14
    python -m app.backup --keep 30 --files    # also archive uploaded files and generated outputs
    python -m app.backup --loop 24            # run forever, one backup every 24 hours (used by docker-compose)

Backups go to BACKUP_DIR (default DATA_DIR/backups). Copy them off the server too: a backup on the same disk does not survive losing the disk.
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import tarfile
import time
from datetime import datetime
from pathlib import Path

from app.core.config import DATA_DIR


def backup_database(dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    source = DATA_DIR / "assistant.db"
    if not source.exists():
        raise SystemExit(f"No database at {source}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw = dest_dir / f"assistant-{stamp}.db"
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(raw)
    try:
        src.backup(dst)   # copies page by page while the app keeps writing; the result is a consistent snapshot
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise SystemExit(f"Backup failed its integrity check: {check}")
    finally:
        dst.close()
        src.close()
    gz = raw.with_suffix(".db.gz")
    with raw.open("rb") as f_in, gzip.open(gz, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    raw.unlink()
    return gz


def backup_files(dest_dir: Path) -> Path | None:
    folders = [DATA_DIR / n for n in ("files", "pages", "artifacts") if (DATA_DIR / n).exists()]
    if not folders:
        return None
    out = dest_dir / f"files-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for folder in folders:
            tar.add(folder, arcname=folder.name)
    return out


def prune(dest_dir: Path, keep: int) -> None:
    for pattern in ("assistant-*.db.gz", "files-*.tar.gz"):
        for old in sorted(dest_dir.glob(pattern))[:-keep] if keep > 0 else []:
            old.unlink(missing_ok=True)


def run_once(keep: int, files: bool) -> None:
    dest = Path(os.environ.get("BACKUP_DIR") or DATA_DIR / "backups")
    made = [backup_database(dest)]
    if files and (extra := backup_files(dest)):
        made.append(extra)
    prune(dest, keep)
    print(datetime.now().isoformat(timespec="seconds"), "backup written:", ", ".join(p.name for p in made), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep", type=int, default=14, help="how many backups of each kind to keep")
    parser.add_argument("--files", action="store_true", help="also archive uploaded files and outputs")
    parser.add_argument("--loop", type=float, metavar="HOURS", help="repeat forever with this pause between backups")
    args = parser.parse_args()
    while True:
        try:
            run_once(args.keep, args.files)
        except Exception as e:   # noqa: BLE001 - a failed night must not stop the loop; the log line is the alarm
            print(datetime.now().isoformat(timespec="seconds"), "BACKUP FAILED:", type(e).__name__, e, flush=True)
            if not args.loop:
                raise
        if not args.loop:
            return
        time.sleep(args.loop * 3600)


if __name__ == "__main__":
    main()
