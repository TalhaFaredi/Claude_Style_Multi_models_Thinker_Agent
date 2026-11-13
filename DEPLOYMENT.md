# Deploying to production

This turns the app into a public, multi-user website: accounts, private data per user, HTTPS on your own domain, spending caps that protect your provider account, and nightly backups. It runs on **one small server** with Docker.

```
Internet ──HTTPS──▶ Caddy ──┬─ /api/*, /health ─▶ backend  (FastAPI + SQLite, one process)
(your domain)               └─ everything else ─▶ frontend (Next.js: landing, sign-in, app)
                                                  backup   (copies the database every 24 h)
```

## What you get, and what you still decide

| Included | Notes |
|---|---|
| Sign-up, sign-in, sign-out, change password, delete account | Passwords are hashed with scrypt. Sessions are random tokens in an HttpOnly cookie, stored only as hashes, ended on password change. |
| Each user's data is private | Chats, files, generated files, memories, settings, usage. Enforced in every query and covered by automated tests that try to read another user's data. |
| Spending protection | Per-user monthly allowance, per-question ceiling, optional global cap. All enforced on the server, so a modified browser cannot raise them. Your provider credit balance is hidden from users. |
| Abuse limits | Rate limits on sign-in/sign-up/reset, per-user and global concurrent-question limits, upload size and per-user storage limits. |
| Website | Landing page, sign-in/up, forgot/reset password, account page, admin page, Terms and Privacy pages, 404/error pages, robots.txt, sitemap. |
| Security hardening | HTTPS with automatic certificates, HSTS, strict Content-Security-Policy, CSRF origin check, no API docs in production, the app refuses to start with an unsafe configuration. |
| Operations | Docker Compose, health checks, daily database backups with retention, admin command-line tool, CI workflow. |
| **You must supply** | A server, a domain, your OpenRouter key, and a **lawyer-reviewed** Terms/Privacy text (the pages are templates until you set `LEGAL_REVIEWED=1`). |

**Not included (be aware):** e-mail address verification, two-factor authentication, payments/billing, and horizontal scaling. See [Limits](#limits-and-when-to-outgrow-this).

## 1. What you need

- A Linux server (Ubuntu 22.04/24.04 is fine): **2 vCPU, 4 GB RAM, 20 GB disk** is a comfortable start. 2 GB works for light use.
- A domain name (for example `assistant.example.com`) with a DNS **A record pointing at the server's IP address**.
- Ports **80 and 443** reachable from the internet (open them in your cloud firewall).
- An [OpenRouter](https://openrouter.ai) API key with credit on it. Set a credit limit on the key in OpenRouter's dashboard as a second safety net.

## 2. Prepare the server

```bash
# Docker (official convenience script)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER     # log out and in again afterwards

# Firewall: SSH, HTTP, HTTPS only
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp
sudo ufw enable
```

Use SSH keys and turn off SSH password login. Keep the server updated (`sudo apt update && sudo apt upgrade`, and consider `unattended-upgrades`).

## 3. Get the code and configure it

```bash
git clone https://github.com/TalhaFaredi/Claude_Style_Multi_models_Thinker_Agent.git assistant
cd assistant
cp .env.production.example .env
nano .env        # fill in SITE_DOMAIN, ACME_EMAIL, OPENROUTER_API_KEY, ADMIN_EMAILS, CONTACT_EMAIL, spending limits
chmod 600 .env
```

The important settings (all are explained in the file itself):

| Setting | Meaning |
|---|---|
| `SITE_DOMAIN`, `ACME_EMAIL` | Your address and the e-mail for certificate notices. |
| `OPENROUTER_API_KEY` | Provider key. Never put it in a `NEXT_PUBLIC_*` variable. |
| `ADMIN_EMAILS` | Accounts created with these addresses become administrators. |
| `DEFAULT_USER_MONTHLY_USD` | Each user's allowance per calendar month. Decide this from your budget: `users × allowance` is your worst case. |
| `MAX_RUN_USD` | Ceiling for a single question. |
| `GLOBAL_MONTHLY_USD` | Hard stop for everyone combined. **Set it.** The server warns at start-up if it is 0. |
| `ALLOW_SIGNUP`, `INVITE_CODE` | Open registration, closed, or invite-only. For a first launch, invite-only is a sensible choice. |
| `SMTP_*` | Optional. Enables "Forgot password" e-mails. |

## 4. Launch

```bash
docker compose up -d --build
docker compose ps                 # all four services should become "healthy"/"running"
docker compose logs -f caddy      # watch the certificate being issued (first start only)
```

The first build downloads dependencies and takes several minutes. When it is done, open `https://your-domain`.

If the backend refuses to start, `docker compose logs backend` says exactly why (for example an unsafe setting). That check is deliberate.

## 5. Create the first administrator

Either sign up on the website with an address listed in `ADMIN_EMAILS`, or from the server:

```bash
docker compose exec backend python -m app.admin create-user you@example.com --admin
```

Then open `/admin` to see users, spending and per-user allowances.

## 6. Check it works (10 minutes)

1. `https://your-domain` shows the landing page with a valid padlock; `http://` redirects to HTTPS.
2. Create a test account in a private window, ask a short question, and see the answer stream in.
3. In `/admin`, the test user's spend appears. Lower their allowance to `0.0001`, ask again: you should get "monthly allowance" message instead of an answer. Reset it.
4. In a second private window sign up as another user and confirm they cannot see the first user's chats.
5. `curl -I https://your-domain` shows `Strict-Transport-Security` and `Content-Security-Policy`.
6. `https://your-domain/docs` returns 404 (API docs are off in production).
7. Use "Forgot password" if you configured SMTP.
8. Read your `/terms` and `/privacy` pages, fix the details, get them reviewed, then set `LEGAL_REVIEWED=1` in `.env` and rebuild the frontend: `docker compose up -d --build frontend`.

## Day-to-day operations

```bash
docker compose logs -f backend                 # application log (secrets are redacted)
docker compose exec backend python -m app.admin list
docker compose exec backend python -m app.admin set-password someone@example.com
docker compose exec backend python -m app.admin set-cap someone@example.com 10
docker compose exec backend python -m app.admin disable someone@example.com
```

### Update to a new version

```bash
cd assistant && git pull
docker compose up -d --build
```

Database changes are additive and applied automatically at start-up. Take a backup first (below) before any major update.

### Backups

The `backup` service writes a consistent snapshot of the database (and your users' uploaded and generated files) every 24 hours into `./backups` on the host and keeps the newest 14 of each. Run one immediately with:

```bash
docker compose exec backup python -m app.backup --files
```

The files in `./backups` are owned by root on the host (read them with `sudo`). **Copy `./backups` off the server regularly** (a backup on the same disk does not survive losing the disk). For example, from another machine: `rsync -a you@server:assistant/backups/ ./assistant-backups/`, or push to object storage with `rclone`. Test a restore at least once.

### Restore

```bash
docker compose stop backend backup
docker compose run --rm --no-deps -v "$PWD/backups:/backups:ro" --entrypoint sh backend -c \
  'rm -f /data/assistant.db-wal /data/assistant.db-shm && gunzip -c /backups/assistant-YYYYMMDD-HHMMSS.db.gz > /data/assistant.db'
# files: tar -xzf backups/files-....tar.gz into the /data volume the same way if needed
docker compose up -d
```

Backups hold users' data; protect the folder like the database itself (and the Privacy page says they are kept 14 days by default; keep the two consistent).

### Rotating secrets

Change `OPENROUTER_API_KEY` in `.env` then `docker compose up -d backend`. Sessions are random tokens in the database, so there is no signing secret to rotate; to sign everybody out, `docker compose exec backend python -c "from app.core import db; db.run('DELETE FROM sessions')"`.

### Moving your existing local data

If you used the app locally before accounts existed, that data belongs to the local single user. Copy `backend/data/` into the `appdata` volume, then give it to an account:

```bash
docker compose exec backend python -m app.admin adopt-legacy you@example.com
```

## Running without Docker

You can run the same pieces by hand (Python 3.12+, Node 22+, Caddy or nginx):

```bash
# backend: one process only (do not add --workers)
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
APP_ENV=production PUBLIC_URL=https://your-domain CORS_ORIGINS=https://your-domain DATA_DIR=/var/lib/assistant \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers

# frontend
cd frontend && npm ci
NEXT_PUBLIC_API_URL=https://your-domain NEXT_PUBLIC_SITE_URL=https://your-domain npm run build:webpack
npm start        # port 3000
```

Run both under systemd, put the `Caddyfile` in front (replace `backend:8000` / `frontend:3000` with `127.0.0.1:8000` / `127.0.0.1:3000`), and put the other settings from `.env.production.example` in the backend's environment.

## Security notes

- Keep `.env` private (`chmod 600`) and out of Git. The repository's `.gitignore` already excludes it.
- The backend container is never published to the internet; only Caddy is. Do not add a `ports:` entry to it.
- The "run code" tool needs Docker access and is **off** in this setup. Do not mount the Docker socket into the backend.
- Users can ask the assistant to read web pages found by search; requests to private/internal addresses are blocked by the tool, and only links from search results can be opened.
- Chat contents are sent to the model providers you configure. The default asks OpenRouter for providers that do not store or train on prompts, which is also what your Privacy page claims. If you change this behaviour, change the page.
- Anyone who can read the server disk or the backups can read all users' chats. Use disk encryption from your host if that matters to your users.
- Rate limits are kept in memory and reset when the backend restarts; they are a brake on abuse, not a firewall. For serious abuse use your host's DDoS protection or put Cloudflare in front.

## Limits, and when to outgrow this

- **One backend process.** Running questions live in memory, so do not start multiple workers or replicas. One process with SQLite comfortably handles dozens of people chatting at once (each question mostly waits on the model provider). `MAX_CONCURRENT_RUNS` is the safety valve.
- **SQLite** is a single file on a single server. It is simple and fast, and the backups above are easy, but there is no automatic failover. If you reach hundreds of concurrent users, move the data layer to PostgreSQL and run state to Redis: that is a code change, not a configuration change.
- **No e-mail verification and no two-factor authentication.** Anyone can sign up with any address (and typing a stranger's address blocks nothing but their sign-up). If this matters for your audience, use `INVITE_CODE` or `ALLOW_SIGNUP=0`.
- **No billing.** Allowances are per calendar month, set by you. Adding payments means adding a payment provider and a plan field on users.
- Time-based limits use the server's clock and the month rolls over at the server's local midnight (UTC in the containers).
