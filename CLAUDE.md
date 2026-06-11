# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Internal project management system for the LENTA retail chain's reconstruction and construction team. Manages store openings, timelines, VPK checklists, SMR schedules, tasks, and manager analytics.

## Commands

```bash
# Run locally (SQLite, no DB setup needed)
uvicorn main:app --reload

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_auth.py -v

# Run a single test by name
pytest tests/test_projects.py::test_create_project -v
```

Tests use SQLite in-memory — no PostgreSQL needed. The `TESTING=1` env var disables CSRF checks.

## Architecture

**Entry point:** `main.py` — registers middleware, routers, 404/500 handlers, and starts background tasks on startup.

**Shared dependencies** (`deps.py`):
- `templates` — single Jinja2Templates instance used by all routes; has `csrf_token` and `media_url` globals, `short_name` filter
- `require_login` / `require_admin` / `require_executive` — FastAPI dependencies for auth
- `limiter` — SlowAPI rate limiter shared across routers

**Routes** (`routes/`): each file is a self-contained FastAPI router imported in `main.py`. All import `templates` and auth deps from `deps.py`.

**Services** (`services/`):
- `background.py` — three async loops: `auto_sync_loop` (Excel sync), `smr_notification_loop` (hourly email), `leader_digest_loop` (daily 09:00 MSK digest)
- `seed.py` — `seed_all(db)` populates managers, users, VPK criteria on first startup
- `excel_import.py` — parses reconstruction/construction Excel files into DB
- `email_service.py` — Resend-based email for SMR notifications and leader digest

**Database:** SQLite locally (`lenta.db`), PostgreSQL on Railway. `database.py` auto-detects from `DATABASE_URL`. Schema migrations run on every startup via `migrations.py` — safe (uses `IF NOT EXISTS`). Never modify migrations manually; add new `ALTER TABLE` entries to `_POSTGRES_MIGRATIONS` list.

**Models** (`models.py`, ~337 lines): `User`, `PhoneWhitelist`, `Manager`, `Project`, `Task`, `VpkCriterion`, `VpkReport`, `SmrSchedule`, `SmrTask`, `ChatMessage`, `AuditLog`, and others. `Manager.is_leader=True` → Гаврин/Комаров (руководители with access to executive dashboard).

## Auth Flow

Two-step: phone whitelist check → password set/enter. Session stored in signed cookie (`starlette.middleware.sessions`). `request.session["user"]` dict contains `id`, `phone`, `display_name`, `is_admin`. `session_version` in DB invalidates sessions after password reset.

## Deploy

Push to `main` → Railway auto-deploys. No manual steps. `RAILWAY_ENVIRONMENT` env var enables `https_only` on sessions.

## Key Conventions

**Corporate colors:** `#FFD200` (Lenta yellow), `#3CB34A` (Lenta green). Used in CSS as `--lenta-yellow` and `--lenta-green`.

**Manager seeding:** `MANAGERS_SEED` in `config.py` defines the fixed team. `services/seed.py:MANAGER_DEFAULTS` maps names to photos/positions/emails. Do not add managers directly to DB — update `MANAGERS_SEED` and `MANAGER_DEFAULTS`.

**Templates:** All extend `base.html`. Pass `user` (from `require_login`) and `request` to every `TemplateResponse`. Error pages (404/500) pass `user=None`.

**Mobile CSS breakpoints:** `d-none d-sm-table-cell` hides table columns on `≤576px`, `d-none d-md-table-cell` on `≤768px`. Bottom nav height `58px` — always include `padding-bottom: calc(58px + env(safe-area-inset-bottom) + 14px)` for scrollable pages.

**Background tasks:** Defined in `services/background.py`, started in `startup()` via `asyncio.create_task()`. Use `database.SessionLocal()` directly (not DI) since they run outside request context.

**Excel import:** Reconstruction Excel has specific column structure (см. `services/excel_import.py`). `SyncConfig` model stores auto-sync paths and intervals.
