# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Internal project management system for the LENTA retail chain's reconstruction and construction team.
Manages store openings, timelines, VPK checklists, SMR schedules, tasks, manager analytics, adaptation cards, and AI chat.

**Stack:** FastAPI 0.115 + SQLAlchemy 2.0 + Jinja2 + Bootstrap 5.3 dark theme  
**Deploy:** Railway.app (PostgreSQL), auto-migrations on startup  
**Tests:** 121 unit/integration tests via pytest (SQLite in-memory) + E2E browser tests via Playwright

---

## Commands

```bash
# Run locally (SQLite, no DB setup needed)
uvicorn main:app --reload

# Run locally with Docker + PostgreSQL (production-like)
docker compose up --build

# Run all tests (SQLite, fast)
pytest tests/ -v

# Run tests against PostgreSQL
TEST_DATABASE_URL=postgresql://lenta:lenta_dev@localhost:5432/lenta pytest tests/ -v

# Load tests (requires: pip install -r requirements-dev.txt)
locust -f tests/locustfile.py --host=http://localhost:8000
# headless: locust -f tests/locustfile.py --host=... --headless -u 20 -r 2 --run-time 60s
```

Tests use SQLite by default — set `TESTING=1` to disable CSRF. Set `TEST_DATABASE_URL` to run against PostgreSQL.

---

## Architecture

### Entry Point

`main.py` — middleware chain (outermost → innermost, Starlette adds in reverse):
1. `GZipMiddleware` — compression
2. `SessionMiddleware` — signed cookie sessions
3. `SessionVersionMiddleware` — invalidates sessions after password reset
4. `CSRFMiddleware` — token check for POST (exempts `/api/`, `/smr/confirm/`, `/vpk/precheck`, `/vpk/submit`)
5. `AdminIPWhitelistMiddleware` — IP whitelist for `/admin/*`
6. `AuditMiddleware` — logs all GET requests by authenticated users
7. `SecurityHeadersMiddleware` — X-Frame-Options, CSP, nosniff, Referrer-Policy

Startup tasks: migrations → seed → 3 async loops (auto_sync, smr_notifications, leader_digest) + APScheduler (backup 03:00, deadline push 09:00 MSK).

### Shared Dependencies (`deps.py`)

- `require_login` → raises HTTPException(302) → `/login` for browser requests
- `require_api_user` → raises HTTPException(401) JSON for AJAX/API calls (use for `/api/*` routes)
- `require_admin` → requires `is_admin=True`
- `require_executive` → `is_admin` OR `is_leader` manager
- `templates` — single Jinja2Templates with `csrf_token`, `media_url` globals, `short_name`/`avatar_color` filters
- `limiter` — SlowAPI shared across routers

### Routes (`routes/`)

25 router modules, each registered in `main.py`. Key routes:
- `auth.py` — phone whitelist → password → 2FA TOTP → WebAuthn
- `projects.py` — CRUD + Excel import/export + stages + comments + attachments
- `vpk.py` — VPK-1/2 checklists, pre-VPK, opening photos, read tracking
- `smr.py` — SMR schedule, milestones, email confirmation tokens
- `adaptation.py` — adaptation cards (XLSX template) + Cloudinary photo upload
- `api.py` — REST endpoints; use `require_api_user` (not `require_login`) here
- `chat.py` — DM + group chat + push notifications via `push_service`
- `ai.py` — Claude/Groq/DeepSeek chat + Excel analysis

### Services (`services/`)

- `background.py` — 3 async loops started in `startup()`
- `push_service.py` — VAPID Web Push; `notify_user()`, `notify_all()`, `send_deadline_push()`
- `backup.py` — `run_pg_backup()` called by APScheduler at 03:00 MSK and by `worker.py`
- `cloud_storage.py` — Cloudinary upload/delete; `upload_photo(content, folder, fname)` → URL
- `email_service.py` — Brevo SMTP; `notify_adaptation_card()`, `notify_smr()`, etc.
- `excel_import.py` — parses reconstruction/construction Excel into Project rows
- `adaptation.py` — generates XLSX from AdaptationCard data

### Database

- SQLite locally (`lenta.db`), PostgreSQL on Railway
- `database.py` auto-detects from `DATABASE_URL`
- `migrations.py` — runs on every startup, idempotent (`IF NOT EXISTS`). Add new migrations to `_POSTGRES_MIGRATIONS` list (also `_SQLITE_MIGRATIONS` for local dev)
- Never modify existing migrations — only append new ones

### Models (`models/`)

Split into modules, all re-exported from `models/__init__.py`:
- `auth.py` — `User`, `PhoneWhitelist`, `WebAuthnCredential`
- `project.py` — `Project` (55+ fields), `ProjectStage`, `ProjectComment`, `OpeningPhoto`, `ProjectHistory`, `ProjectAttachment`, `SyncConfig`
- `task.py` — `Task`, `TaskPhoto`, `TaskNotification`
- `vpk.py` — `VpkCriterion`, `VpkReport`, `VpkReportItem`, `VpkReportRead`, `PreVpkReport`, `PreVpkReportItem`
- `smr.py` — `SmrSchedule`, `SmrTask`, `SmrContact`, `SmrConfirmation`
- `misc.py` — `Manager`, `ChatMessage`, `AiChatMessage`, `AuditLog`, `PushSubscription`, `KsoObject`, `KsoSchedule`
- `adaptation.py` — `AdaptationCard`, `AdaptationPhoto`
- `recon.py` — `ReconStageStatus`

`Manager.is_leader=True` → Гаврин/Комаров (executive dashboard access).

---

## Auth Flow

1. Phone whitelist check (`PhoneWhitelist`)
2. Password set (first time) or enter (existing)
3. Optional: TOTP 2FA (`User.totp_enabled`)
4. Optional: WebAuthn biometric (passkeys)
5. Session: `request.session["user"]` = `{id, phone, display_name, is_admin, sv}`
6. `sv` (session_version) compared to DB — mismatch forces re-login

---

## Security

- Passwords: PBKDF2-SHA256 (Argon2 fallback)
- CSRF: all POST forms, token in `<meta name="csrf-token">`, auto-injected by JS
- Rate limits: 5/min login, 20/min phone check, 10/min 2FA
- Admin IP whitelist: `ADMIN_IP_WHITELIST` env var (comma-separated)
- Audit log: every authenticated GET request → `AuditLog` table
- CSP headers: `script-src 'self' 'nonce-{nonce}' cdn.jsdelivr.net` — no `'unsafe-inline'`; all scripts use nonce injected by `SecurityHeadersMiddleware`
- Push notifications: VAPID keys in Railway env vars (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`)

---

## Key Conventions

**Corporate colors:** `#FFD200` (Lenta yellow), `#3CB34A` (Lenta green). CSS vars: `--lenta-yellow`, `--lenta-green`.

**Templates:** All extend `base.html`. Always pass `user` and `request` to `TemplateResponse`. Error pages pass `user=None`.

**Mobile CSS:** Bottom nav height `58px` — include `padding-bottom: calc(58px + env(safe-area-inset-bottom) + 14px)` on scrollable pages. Use `d-none d-lg-none` for mobile-only elements.

**Background tasks:** Use `database.SessionLocal()` directly inside `services/background.py` (not DI), since they run outside request context. Always call `db.close()` in `finally`.

**Worker process:** `worker.py` runs independently via Procfile `worker:` — handles backup and deadline push via APScheduler. Don't duplicate these jobs in `main.py` startup if `worker.py` is running.

**Email:** Notify email goes to `NOTIFY_PRECHECK_EMAIL` env var (default: `denis.mesmer@lenta.com`). Never send to managers without explicit instruction.

**Manager seeding:** Update `config.py:MANAGERS_SEED` and `services/seed.py:MANAGER_DEFAULTS`. Don't add managers directly to DB.

**Excel import:** Reconstruction Excel has specific column structure — see `services/excel_import.py`. `SyncConfig` stores auto-sync paths/intervals.

**Gantt:** frappe-gantt 0.6.1 loaded from CDN. Drag-and-drop calls `POST /api/stages/{id}/dates` with JSON body `{start, end}`. Debounced 700ms.

**Service Worker:** Served at `/sw.js` (NOT `/static/sw.js`) via dedicated FastAPI route with `Service-Worker-Allowed: /` header. Scope must be `/` for push to work.

**CSS cache busting:** Update version string in `base.html`: `style.css?v=YYYYMMDD`.

---

## Deploy

Railway NIXPACKS auto-builds on push to `main`. Two processes:
- `web`: uvicorn main:app
- `worker`: python worker.py (backup + deadline push scheduler)

GitHub Actions CI runs `pytest` on push and deploys via `railway up` on merge to `main`.  
Set `RAILWAY_TOKEN` secret in GitHub repository settings.

---

## Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `SECRET_KEY` | ✅ | Session signing key |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `ADMIN_PHONE` | ✅ | First admin phone (+7XXXXXXXXXX) |
| `APP_DOMAIN` | ✅ | Domain for WebAuthn (e.g. lenta-web.railway.app) |
| `APP_URL` | ✅ | Full URL (https://lenta-web.railway.app) |
| `CLOUDINARY_CLOUD_NAME` | — | Photo storage |
| `CLOUDINARY_API_KEY` | — | Photo storage |
| `CLOUDINARY_API_SECRET` | — | Photo storage |
| `GROQ_API_KEY` | — | AI assistant (free) |
| `ANTHROPIC_API_KEY` | — | Claude AI |
| `SMTP_HOST/PORT/USER/PASS` | — | Email via Brevo |
| `NOTIFY_PRECHECK_EMAIL` | — | VPK/adaptation email recipient |
| `VAPID_PUBLIC_KEY` | — | Web Push |
| `VAPID_PRIVATE_KEY` | — | Web Push |
| `SENTRY_DSN` | — | Error tracking |
| `ADMIN_IP_WHITELIST` | — | Comma-separated IPs for /admin/* |
