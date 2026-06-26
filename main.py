"""Application entry point — FastAPI app, middleware stack, startup tasks."""
import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class _NoHealthFilter(logging.Filter):
    """Suppresses high-frequency health-check lines from uvicorn's access log."""

    _SKIP = ("/api/ping", "/api/online")

    def filter(self, record: logging.LogRecord) -> bool:
        return not any(p in record.getMessage() for p in self._SKIP)


logging.getLogger("uvicorn.access").addFilter(_NoHealthFilter())
# ─────────────────────────────────────────────────────────────────────────────

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

import database
import models
from deps import limiter, templates
from middleware import (
    AdminIPWhitelistMiddleware,
    AuditMiddleware,
    CSRFMiddleware,
    SecurityHeadersMiddleware,
    SessionVersionMiddleware,
)
from migrations import run_postgres_migrations, run_sqlite_migrations
from services.background import auto_sync_loop, leader_digest_loop, smr_notification_loop
from services.online import ONLINE_TIMEOUT, ONLINE_USERS
from services.seed import seed_all

logger = logging.getLogger(__name__)

_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.2,
        environment=os.getenv("RAILWAY_ENVIRONMENT", "development"),
        send_default_pii=False,
    )

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "SECRET_KEY is not set — sessions will reset on every restart. "
        "Set SECRET_KEY in environment variables."
    )

_SESSION_MAX_AGE    = 7 * 24 * 60 * 60  # 7 days in seconds
_GZIP_MIN_SIZE      = 1_000             # bytes
_ADMIN_IP_WHITELIST = [
    ip.strip() for ip in os.getenv("ADMIN_IP_WHITELIST", "").split(",") if ip.strip()
]

app = FastAPI(title="Лента — Управление проектами")

# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(
        "404.html", {"request": request, "user": None}, status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(
        "500.html", {"request": request, "user": None}, status_code=500,
    )


# ── Middleware stack (outermost → innermost, Starlette adds in reverse) ───────
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(AdminIPWhitelistMiddleware, whitelist=_ADMIN_IP_WHITELIST)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SessionVersionMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=_SESSION_MAX_AGE,
    same_site="lax",
    https_only=bool(os.getenv("RAILWAY_ENVIRONMENT")),
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(GZipMiddleware, minimum_size=_GZIP_MIN_SIZE)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Special routes ────────────────────────────────────────────────────────────

@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    """Serves the Service Worker from the root scope so push notifications work."""
    return FileResponse(
        "static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache, no-store"},
    )


@app.get("/clear-sw", include_in_schema=False)
async def clear_sw():
    """One-visit page that unregisters the Service Worker and clears all caches."""
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Сброс кэша — Лента.PM</title>
<style>
body{font-family:-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;
     display:flex;flex-direction:column;align-items:center;justify-content:center;
     min-height:100vh;margin:0;padding:24px;text-align:center}
h2{color:#3CB34A;margin-bottom:8px}
#status{color:#94a3b8;margin:16px 0}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;
     background:#3CB34A;animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
a{color:#3CB34A;font-weight:700}
</style>
</head>
<body>
<h2>⚡ Сброс кэша Лента.PM</h2>
<p id="status"><span class="dot"></span> Удаляем Service Worker...</p>
<script>
(async function () {
    var s = document.getElementById('status'), done = [];
    try {
        if ('serviceWorker' in navigator) {
            var regs = await navigator.serviceWorker.getRegistrations();
            for (var r of regs) await r.unregister();
            done.push('SW удалён ✓');
        }
        if ('caches' in window) {
            var keys = await caches.keys();
            for (var k of keys) await caches.delete(k);
            done.push('Кэш очищен ✓');
        }
        s.innerHTML = done.join(' &nbsp;|&nbsp; ') + '<br><br>Готово! Перенаправляем...';
        setTimeout(function () { location.replace('/'); }, 1200);
    } catch (e) {
        s.innerHTML = 'Ошибка: ' + e.message + '<br><a href="/">← На главную</a>';
    }
}());
</script>
</body>
</html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


# ── Routers ───────────────────────────────────────────────────────────────────
from routes.adaptation import router as adaptation_router
from routes.admin import router as admin_router
from routes.ai import router as ai_router
from routes.analytics import router as analytics_router
from routes.api import router as api_router
from routes.auth import router as auth_router
from routes.case import router as case_router
from routes.chat import router as chat_router
from routes.dashboard import router as dashboard_router
from routes.deadlines import router as deadlines_router
from routes.executive import router as executive_router
from routes.help import router as help_router
from routes.kanban import router as kanban_router
from routes.kso import router as kso_router
from routes.leader import router as leader_router
from routes.managers import router as managers_router
from routes.map import router as map_router
from routes.presence import router as presence_router
from routes.projects import router as projects_router
from routes.reconstruction import router as reconstruction_router
from routes.search import router as search_router
from routes.sections import router as sections_router
from routes.smr import router as smr_router
from routes.stats import router as stats_router
from routes.sync import router as sync_router
from routes.tasks import router as tasks_router
from routes.tools import router as tools_router
from routes.vpk import router as vpk_router

for _router in [
    auth_router, dashboard_router, projects_router, sections_router,
    kso_router, tasks_router, managers_router, deadlines_router,
    vpk_router, stats_router, admin_router, chat_router,
    ai_router, api_router, sync_router, smr_router, leader_router,
    executive_router, help_router, case_router, reconstruction_router,
    search_router, adaptation_router, analytics_router, map_router,
    kanban_router, presence_router, tools_router,
]:
    app.include_router(_router)


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    models.Base.metadata.create_all(bind=database.engine)

    if "postgresql" in str(database.DATABASE_URL):
        run_postgres_migrations(database.engine)

    # Restore recently-online users from DB into the in-memory set
    try:
        cutoff = datetime.utcnow() - timedelta(seconds=ONLINE_TIMEOUT)
        with database.db_session() as db:
            recent = db.query(models.User.display_name, models.User.last_seen).filter(
                models.User.last_seen >= cutoff,
                models.User.display_name.isnot(None),
            ).all()
            for name, ts in recent:
                if name:
                    ONLINE_USERS[name] = ts
        logger.info("Restored %d online users from DB", len(ONLINE_USERS))
    except Exception as exc:
        logger.debug("Online-user restore skipped: %s", exc)

    if "sqlite" in str(database.DATABASE_URL):
        run_sqlite_migrations(database.engine)

    db = database.SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()

    asyncio.create_task(auto_sync_loop())
    asyncio.create_task(smr_notification_loop())
    asyncio.create_task(leader_digest_loop())

    if "postgresql" in str(database.DATABASE_URL):
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            from services.backup import run_pg_backup
            from services.push_service import send_deadline_push

            def _deadline_push_job() -> None:
                _db = next(database.get_db())
                try:
                    send_deadline_push(_db)
                finally:
                    _db.close()

            scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
            scheduler.add_job(run_pg_backup,       "cron", hour=3, minute=0)
            scheduler.add_job(_deadline_push_job,  "cron", hour=9, minute=0)
            scheduler.start()
            logger.info("APScheduler started: backup 03:00, deadline push 09:00 MSK")
        except ImportError:
            logger.warning("apscheduler not installed — scheduled backup unavailable")
