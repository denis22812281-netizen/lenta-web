import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import parse_qs

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.2,
        environment=os.getenv("RAILWAY_ENVIRONMENT", "development"),
        send_default_pii=False,
    )

import database
import models
from deps import limiter, templates
from migrations import run_postgres_migrations, run_sqlite_migrations
from services.background import auto_sync_loop, smr_notification_loop, leader_digest_loop
from services.online import ONLINE_USERS, ONLINE_TIMEOUT
from services.seed import seed_all

logger = logging.getLogger(__name__)

app = FastAPI(title="Лента — Управление проектами")


class CSRFMiddleware(BaseHTTPMiddleware):
    """Проверяет CSRF-токен для всех POST-форм (кроме API и логина)."""
    _EXEMPT = ("/api/", "/login/", "/smr/confirm/", "/import-reconstruct", "/import-construction",
               "/vpk/precheck", "/vpk/submit", "/opening/upload", "/opening/send-report",
               "/admin/adaptation-template")

    async def dispatch(self, request: Request, call_next):
        if os.getenv("TESTING") == "1":
            return await call_next(request)
        if request.method == "POST":
            path = request.url.path
            ct   = request.headers.get("content-type", "")
            if not any(path.startswith(e) for e in self._EXEMPT):
                submitted = None
                try:
                    if ct.startswith("multipart/"):
                        form = await request.form()
                        submitted = form.get("csrf_token")
                    else:
                        body = await request.body()
                        params = parse_qs(body.decode("utf-8"))
                        submitted = (params.get("csrf_token") or [None])[0]
                except Exception:
                    submitted = None
                expected = request.session.get("csrf_token", "")
                if not (expected and submitted
                        and secrets.compare_digest(str(submitted), expected)):
                    logger.warning("CSRF fail: path=%s ip=%s",
                                   path, request.client.host if request.client else "?")
                    return HTMLResponse(
                        "<h2>403 Forbidden</h2><p>Неверный CSRF-токен. "
                        "<a href='javascript:history.back()'>Назад</a></p>",
                        status_code=403)
        return await call_next(request)


SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning("SECRET_KEY не задан! Сессии будут сброшены при каждом рестарте. "
                   "Задайте SECRET_KEY в переменных окружения.")


class SessionVersionMiddleware(BaseHTTPMiddleware):
    """Инвалидирует сессию если session_version не совпадает с БД (после сброса пароля)."""
    _SKIP = ("/login", "/static", "/api/ping")

    async def dispatch(self, request: Request, call_next):
        user = request.session.get("user")
        if user and not any(request.url.path.startswith(s) for s in self._SKIP):
            sv_cookie = user.get("sv", 1)
            try:
                with database.db_session() as db:
                    db_user = db.query(models.User).filter(
                        models.User.id == user["id"]).first()
                    if db_user and (db_user.session_version or 1) != sv_cookie:
                        request.session.pop("user", None)
                        from fastapi.responses import RedirectResponse as RR
                        return RR("/login", status_code=302)
            except Exception:
                pass
        return await call_next(request)


class AdminIPWhitelistMiddleware(BaseHTTPMiddleware):
    """Блокирует доступ к /admin/* если IP не в белом списке (ADMIN_IP_WHITELIST env)."""
    _ADMIN_PREFIX = ("/admin/",)

    def __init__(self, app, whitelist: list[str]):
        super().__init__(app)
        self._ips = set(ip.strip() for ip in whitelist if ip.strip())

    async def dispatch(self, request: Request, call_next):
        if not self._ips:
            return await call_next(request)
        path = request.url.path
        if any(path.startswith(p) for p in self._ADMIN_PREFIX):
            user = request.session.get("user")
            if user and user.get("is_admin"):
                client_ip = (
                    request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                    or (request.client.host if request.client else "")
                )
                if client_ip not in self._ips:
                    logger.warning("Admin IP blocked: ip=%s path=%s user=%s",
                                   client_ip, path, user.get("display_name"))
                    return HTMLResponse(
                        "<h2>403 Forbidden</h2>"
                        "<p>Ваш IP-адрес не разрешён для доступа к панели администратора.</p>"
                        "<p><a href='/'>На главную</a></p>",
                        status_code=403,
                    )
        return await call_next(request)


class AuditMiddleware(BaseHTTPMiddleware):
    """Записывает посещения страниц авторизованными пользователями."""
    _SKIP_PREFIX = ("/static", "/api/ping", "/api/online", "/favicon", "/admin/audit")
    _SKIP_EXT    = (".css", ".js", ".png", ".ico", ".jpg", ".woff2", ".svg", ".webp")

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            if request.method != "GET":
                return response
            path = request.url.path
            if (any(path.startswith(s) for s in self._SKIP_PREFIX)
                    or any(path.endswith(e) for e in self._SKIP_EXT)):
                return response
            user = request.session.get("user")
            if not user:
                return response
            user_name  = user.get("display_name", "")
            user_phone = user.get("phone", "")
            ip         = request.client.host if request.client else ""

            def _write():
                db = database.SessionLocal()
                try:
                    db.add(models.AuditLog(
                        user_name=user_name, user_phone=user_phone,
                        path=path, ip=ip,
                    ))
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()

            asyncio.get_running_loop().run_in_executor(None, _write)
        except Exception:
            pass
        return response


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request, "user": None}, status_code=404)

@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return templates.TemplateResponse("500.html", {"request": request, "user": None}, status_code=500)

_ADMIN_IP_WHITELIST = [ip.strip() for ip in os.getenv("ADMIN_IP_WHITELIST", "").split(",") if ip.strip()]

app.add_middleware(AuditMiddleware)
app.add_middleware(AdminIPWhitelistMiddleware, whitelist=_ADMIN_IP_WHITELIST)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SessionVersionMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400 * 7,
                   same_site="lax", https_only=bool(os.getenv("RAILWAY_ENVIRONMENT")))
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── Роутеры ─────────────────────────────────────────────────────────────────
from routes.auth      import router as auth_router
from routes.dashboard import router as dashboard_router
from routes.projects  import router as projects_router
from routes.sections  import router as sections_router
from routes.kso       import router as kso_router
from routes.tasks     import router as tasks_router
from routes.managers  import router as managers_router
from routes.deadlines import router as deadlines_router
from routes.vpk       import router as vpk_router
from routes.stats     import router as stats_router
from routes.admin     import router as admin_router
from routes.chat      import router as chat_router
from routes.ai        import router as ai_router
from routes.api       import router as api_router
from routes.sync      import router as sync_router
from routes.smr       import router as smr_router
from routes.leader    import router as leader_router
from routes.executive import router as executive_router
from routes.help      import router as help_router
from routes.case           import router as case_router
from routes.reconstruction import router as reconstruction_router
from routes.search         import router as search_router
from routes.adaptation     import router as adaptation_router
from routes.analytics      import router as analytics_router

for r in [auth_router, dashboard_router, projects_router, sections_router,
          kso_router, tasks_router, managers_router, deadlines_router,
          vpk_router, stats_router, admin_router, chat_router,
          ai_router, api_router, sync_router, smr_router, leader_router,
          executive_router, help_router, case_router, reconstruction_router,
          search_router, adaptation_router, analytics_router]:
    app.include_router(r)


# ─── Startup ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    models.Base.metadata.create_all(bind=database.engine)

    if "postgresql" in str(database.DATABASE_URL):
        run_postgres_migrations(database.engine)

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
    except Exception as e:
        logger.debug("online restore skipped: %s", e)

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

    # Автобэкап БД + Push-дедлайны каждую ночь
    if "postgresql" in str(database.DATABASE_URL):
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from services.backup import run_pg_backup
            from services.push_service import send_deadline_push

            _scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
            _scheduler.add_job(run_pg_backup, "cron", hour=3, minute=0)

            def _run_deadline_push():
                db = next(database.get_db())
                try:
                    send_deadline_push(db)
                finally:
                    db.close()

            _scheduler.add_job(_run_deadline_push, "cron", hour=9, minute=0)
            _scheduler.start()
            logger.info("APScheduler: бэкап 03:00, push-дедлайны 09:00 МСК")
        except ImportError:
            logger.warning("apscheduler не установлен — авто-бэкап недоступен")
