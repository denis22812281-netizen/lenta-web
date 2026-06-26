import asyncio
import logging
import os
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import parse_qs

from dotenv import load_dotenv

load_dotenv()

# ── Structured logging ────────────────────────────────────────────────────────
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

class _NoHealthFilter(logging.Filter):
    """Suppress noisy health-check entries from uvicorn access log."""
    _SKIP = ("/api/ping", "/api/online")
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in self._SKIP)

logging.getLogger("uvicorn.access").addFilter(_NoHealthFilter())
# ─────────────────────────────────────────────────────────────────────────────

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

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
from services.background import auto_sync_loop, leader_digest_loop, smr_notification_loop
from services.online import ONLINE_TIMEOUT, ONLINE_USERS
from services.seed import seed_all

logger = logging.getLogger(__name__)

app = FastAPI(title="Лента — Управление проектами")


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection for all POST requests except public endpoints.

    Accepts the token from either:
      - X-CSRFToken header (AJAX / multipart fetch calls)
      - csrf_token field in urlencoded form body (traditional HTML forms)
    Checking the header first means we never need to read multipart bodies
    here, so multipart upload routes no longer need exemptions.
    """
    _EXEMPT = ("/api/", "/login/", "/smr/confirm/")

    async def dispatch(self, request: Request, call_next):
        if os.getenv("TESTING") == "1":
            return await call_next(request)
        if request.method == "POST":
            path = request.url.path
            if not any(path.startswith(e) for e in self._EXEMPT):
                submitted = request.headers.get("X-CSRFToken")
                if not submitted:
                    # Fallback: urlencoded body (standard HTML <form> POST)
                    ct = request.headers.get("content-type", "")
                    if "application/x-www-form-urlencoded" in ct or not ct:
                        try:
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


_SCRIPT_NONCE_RE = re.compile(rb"<script(?![^>]*\bnonce\b)", re.IGNORECASE)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Добавляет security-заголовки и инжектирует CSP nonce во все <script> теги."""
    _CSP_TMPL = (
        "default-src 'self'; "
        "script-src 'self' 'nonce-{{nonce}}' cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
        "img-src 'self' data: blob: res.cloudinary.com *.cloudinary.com "
        "*.tile.openstreetmap.org *.basemaps.cartocdn.com; "
        "connect-src 'self' fcm.googleapis.com *.googleapis.com; "
        "font-src 'self' cdn.jsdelivr.net fonts.gstatic.com; "
        "frame-ancestors 'none'; "
        "object-src 'none';"
    )

    async def dispatch(self, request: Request, call_next):
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response = await call_next(request)

        base_headers = {
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
            "X-XSS-Protection": "1; mode=block",
        }
        if os.getenv("RAILWAY_ENVIRONMENT"):
            base_headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        ct = response.headers.get("content-type", "")
        if "text/html" not in ct:
            # Static assets with version strings → cache 1 year in browser
            if request.url.path.startswith("/static/"):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            for k, v in base_headers.items():
                response.headers[k] = v
            return response

        # HTML pages are user-specific — never cache
        base_headers["Cache-Control"] = "no-store"

        # Читаем тело, инжектируем nonce во все <script> теги
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        body = b"".join(chunks)

        nonce_b = nonce.encode("ascii")
        body = _SCRIPT_NONCE_RE.sub(b'<script nonce="' + nonce_b + b'"', body)

        base_headers["Content-Security-Policy"] = self._CSP_TMPL.replace("{{nonce}}", nonce)

        from starlette.responses import Response as PlainResponse
        new_resp = PlainResponse(content=body, status_code=response.status_code, media_type=ct)
        for k, v in response.headers.items():
            if k.lower() not in ("content-length", "content-type"):
                new_resp.headers[k] = v
        for k, v in base_headers.items():
            new_resp.headers[k] = v
        return new_resp


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

app.add_middleware(SecurityHeadersMiddleware)
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


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    """Service Worker должен отдаваться с корневого пути для скоупа /."""
    from fastapi.responses import FileResponse
    return FileResponse("static/sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/",
                                 "Cache-Control": "no-cache, no-store"})


@app.get("/clear-sw", include_in_schema=False)
async def clear_sw():
    """Страница для принудительного сброса Service Worker и кэша в браузере."""
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Сброс кэша — Лента.PM</title>
<style>
body{font-family:-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;
     display:flex;flex-direction:column;align-items:center;justify-content:center;
     min-height:100vh;margin:0;padding:24px;text-align:center;}
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
(async function() {
    var s = document.getElementById('status');
    var steps = [];
    try {
        if ('serviceWorker' in navigator) {
            var regs = await navigator.serviceWorker.getRegistrations();
            for (var r of regs) { await r.unregister(); }
            steps.push('SW удалён ✓');
        }
        if ('caches' in window) {
            var keys = await caches.keys();
            for (var k of keys) { await caches.delete(k); }
            steps.push('Кэш очищен ✓');
        }
        s.innerHTML = steps.join(' &nbsp;|&nbsp; ') + '<br><br>Готово! Перенаправляем...';
        setTimeout(function(){ location.replace('/'); }, 1200);
    } catch(e) {
        s.innerHTML = 'Ошибка: ' + e.message + '<br><a href="/">← На главную</a>';
    }
})();
</script>
</body>
</html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


# ─── Роутеры ─────────────────────────────────────────────────────────────────
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

for r in [auth_router, dashboard_router, projects_router, sections_router,
          kso_router, tasks_router, managers_router, deadlines_router,
          vpk_router, stats_router, admin_router, chat_router,
          ai_router, api_router, sync_router, smr_router, leader_router,
          executive_router, help_router, case_router, reconstruction_router,
          search_router, adaptation_router, analytics_router, map_router,
          kanban_router, presence_router, tools_router]:
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
