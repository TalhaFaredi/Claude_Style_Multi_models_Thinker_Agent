"""Operator tool. Run inside the backend folder / container:

    python -m app.admin create-user you@example.com --admin
    python -m app.admin set-password you@example.com
    python -m app.admin list
    python -m app.admin disable|enable you@example.com
    python -m app.admin set-cap you@example.com 10        # monthly USD for this user ("default" = server default)
    python -m app.admin delete-user you@example.com       # deletes the account AND all its chats, files and memory
    python -m app.admin adopt-legacy you@example.com      # give a user the single-user data from before accounts existed

Passwords are read from a prompt (or the ADMIN_PASSWORD environment variable for scripts), never from the command line.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from app.core import auth, db, usage
from app.core.auth import AuthError


def _password(confirm: bool = True) -> str:
    env = os.environ.get("ADMIN_PASSWORD")
    if env:
        return env
    first = getpass.getpass("Password: ")
    if confirm and first != getpass.getpass("Repeat password: "):
        sys.exit("The passwords do not match.")
    return first


def _user_row(email: str):
    row = db.one("SELECT * FROM users WHERE email=?", (auth.normalize_email(email),))
    if not row:
        sys.exit(f"No user with e-mail {email}.")
    return row


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("email")
    c.add_argument("--admin", action="store_true")
    sub.add_parser("list")
    for name in ("set-password", "disable", "enable", "delete-user", "adopt-legacy"):
        sub.add_parser(name).add_argument("email")
    cap = sub.add_parser("set-cap")
    cap.add_argument("email")
    cap.add_argument("usd", help='monthly allowance in USD, or "default"')
    args = parser.parse_args(argv)

    db.conn()
    try:
        if args.cmd == "create-user":
            user = auth.create_user(args.email, _password(), is_admin=args.admin)
            print(f"Created {user.email} (id {user.id}{', admin' if user.is_admin else ''}).")
        elif args.cmd == "list":
            print(f"{'id':>4}  {'e-mail':<36} {'admin':<5} {'off':<3} {'cap $':>7} {'spent $':>8}  last login")
            start = usage.month_start()
            for r in db.q("SELECT * FROM users ORDER BY id"):
                spent = db.one("SELECT COALESCE(SUM(cost),0) c FROM calls WHERE user_id=? AND ts>=?", (r["id"], start))["c"]
                last = "never" if not r["last_login"] else __import__("datetime").datetime.fromtimestamp(r["last_login"]).strftime("%Y-%m-%d %H:%M")
                cap_s = "default" if r["monthly_cap"] is None else f"{r['monthly_cap']:.2f}"
                print(f"{r['id']:>4}  {r['email']:<36} {'yes' if r['is_admin'] else '':<5} {'yes' if r['disabled'] else '':<3} {cap_s:>7} {spent:>8.4f}  {last}")
        elif args.cmd == "set-password":
            row = _user_row(args.email)
            auth.set_password(row["id"], _password())
            print("Password changed. The user was signed out everywhere.")
        elif args.cmd in ("disable", "enable"):
            row = _user_row(args.email)
            db.run("UPDATE users SET disabled=? WHERE id=?", (int(args.cmd == "disable"), row["id"]))
            if args.cmd == "disable":
                auth.end_sessions(row["id"])
            print(f"{args.email} {'disabled' if args.cmd == 'disable' else 'enabled'}.")
        elif args.cmd == "set-cap":
            row = _user_row(args.email)
            value = None if args.usd == "default" else float(args.usd)
            db.run("UPDATE users SET monthly_cap=? WHERE id=?", (value, row["id"]))
            print("Monthly allowance set to", "the server default" if value is None else f"${value:.2f}")
        elif args.cmd == "delete-user":
            row = _user_row(args.email)
            if input(f"Delete {args.email} and ALL of their chats, files and memories? Type the e-mail to confirm: ").strip().lower() != row["email"]:
                sys.exit("Cancelled.")
            from app.api.auth import purge_user_data
            print("Deleted.", purge_user_data(row["id"]))
        elif args.cmd == "adopt-legacy":
            row = _user_row(args.email)
            moved = {}
            with db.tx() as conn:
                for table in ("chats", "facts", "calls", "artifacts"):
                    moved[table] = conn.execute(f"UPDATE {table} SET user_id=? WHERE user_id=0", (row["id"],)).rowcount
                for r in conn.execute("SELECT key FROM settings WHERE key NOT LIKE 'u%:%'").fetchall():
                    conn.execute("INSERT OR IGNORE INTO settings(key,value) SELECT ?,value FROM settings WHERE key=?", (db.setting_key(r["key"], row["id"]), r["key"]))
            print("Moved to", args.email, moved)
    except AuthError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
