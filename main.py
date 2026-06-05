import asyncio
import logging
import os
from dotenv import load_dotenv
load_dotenv()
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

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
from config import MANAGERS_SEED
from deps import limiter
from services.excel_import import import_reconstruct_excel, import_construction_excel, parse_excel_file
from services.online import ONLINE_USERS
from services.email_service import send_smr_deadline_notification

logger = logging.getLogger(__name__)

app = FastAPI(title="Лента — Управление проектами")


class CSRFMiddleware(BaseHTTPMiddleware):
    """Проверяет CSRF-токен для всех POST-форм (кроме API и логина)."""
    _EXEMPT = ("/api/", "/login/", "/smr/confirm/")
    _SKIP_CONTENT = ("multipart/", "application/json")

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST":
            path = request.url.path
            ct   = request.headers.get("content-type", "")
            if (not any(path.startswith(e) for e in self._EXEMPT)
                    and not any(ct.startswith(s) for s in self._SKIP_CONTENT)):
                body = await request.body()
                try:
                    params = parse_qs(body.decode("utf-8"))
                    submitted = (params.get("csrf_token") or [None])[0]
                except Exception:
                    submitted = None
                expected = request.session.get("csrf_token", "")
                if not (expected and submitted
                        and secrets.compare_digest(submitted, expected)):
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
    logger.warning("SECRET_KEY не задан! Сессии будут сброшены при каждом рестарте. Задайте SECRET_KEY в переменных окружения.")


class SessionVersionMiddleware(BaseHTTPMiddleware):
    """Инвалидирует сессию если session_version не совпадает с БД (после сброса пароля)."""
    _SKIP = ("/login", "/static", "/webauthn", "/api/ping")

    async def dispatch(self, request: Request, call_next):
        user = request.session.get("user")
        if user and not any(request.url.path.startswith(s) for s in self._SKIP):
            sv_cookie = user.get("sv", 1)
            try:
                db = database.SessionLocal()
                db_user = db.query(models.User).filter(
                    models.User.id == user["id"]).first()
                if db_user and (db_user.session_version or 1) != sv_cookie:
                    request.session.pop("user", None)
                    from fastapi.responses import RedirectResponse as RR
                    return RR("/login", status_code=302)
            except Exception:
                pass
            finally:
                db.close()
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

            asyncio.get_event_loop().run_in_executor(None, _write)
        except Exception:
            pass
        return response


app.add_middleware(AuditMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SessionVersionMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400 * 7,
                   same_site="lax", https_only=bool(os.getenv("RAILWAY_ENVIRONMENT")))
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── Подключаем роутеры ──────────────────────────────────────────────────────
from routes.auth      import router as auth_router
from routes.webauthn  import router as webauthn_router
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

for r in [auth_router, webauthn_router, dashboard_router, projects_router, sections_router,
          kso_router, tasks_router, managers_router, deadlines_router,
          vpk_router, stats_router, admin_router, chat_router,
          ai_router, api_router, sync_router, smr_router, leader_router]:
    app.include_router(r)


# ─── Фоновая задача авто-синхронизации ───────────────────────────────────────
async def auto_sync_loop():
    while True:
        await asyncio.sleep(60)
        try:
            db = database.SessionLocal()
            try:
                configs = db.query(models.SyncConfig).filter(
                    models.SyncConfig.auto_sync == True,
                    models.SyncConfig.file_path != "").all()
                for cfg in configs:
                    if not cfg.last_synced:
                        should_sync = True
                    else:
                        elapsed = (datetime.utcnow() - cfg.last_synced).total_seconds() / 60
                        should_sync = elapsed >= cfg.sync_interval_minutes
                    if should_sync:
                        path = Path(cfg.file_path).resolve()
                        if (path.exists() and path.suffix in ('.xlsx', '.xls', '.xlsm')
                                and not str(path).startswith(('/etc', '/proc', '/sys', 'C:\\Windows'))):
                            try:
                                content = path.read_bytes()
                                if cfg.project_type == "Реконструкция":
                                    result = import_reconstruct_excel(content, db)
                                elif cfg.project_type == "Констракшн":
                                    result = import_construction_excel(content, db)
                                else:
                                    result = parse_excel_file(content, cfg.project_type, None, db)
                                cfg.last_synced = datetime.utcnow()
                                cfg.last_status = f"OK: создано {result['created']}, обновлено {result['updated']}"
                            except Exception as e:
                                cfg.last_status = f"Ошибка: {str(e)[:100]}"
                        else:
                            cfg.last_status = f"Файл не найден: {cfg.file_path}"
                        db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("[auto_sync_loop] ошибка: %s", e)


# ─── Авто-уведомления по графику СМР ─────────────────────────────────────────

async def smr_notification_loop():
    """
    Каждый час проверяет задачи графика СМР, у которых end_plan = сегодня.
    Если у задачи указан notify_email1/email2 и ещё не отправляли сегодня —
    шлёт письмо с кнопками Выполнено / Не выполнено.
    """
    import secrets as _sec
    _APP_URL = os.getenv("APP_URL", "https://lenta-web-production.up.railway.app").rstrip("/")

    while True:
        await asyncio.sleep(3600)   # раз в час
        try:
            from datetime import date as _date
            today = _date.today()
            db = database.SessionLocal()
            try:
                tasks = db.query(models.SmrTask).filter(
                    models.SmrTask.end_plan == today,
                    models.SmrTask.status != "Выполнено",
                    (models.SmrTask.notified_date == None) |
                    (models.SmrTask.notified_date < today),
                ).all()

                for task in tasks:
                    emails = [e for e in [task.notify_email1, task.notify_email2] if e]
                    if not emails:
                        continue
                    proj = task.schedule.project if task.schedule else None
                    if not proj:
                        continue

                    for email in emails:
                        token   = _sec.token_hex(32)
                        db.add(models.SmrConfirmation(
                            task_id=task.id, token=token, email=email))
                        db.flush()
                        send_smr_deadline_notification(
                            to_email=email,
                            task_name=task.name,
                            project_name=proj.name,
                            tk_number=proj.tk_number,
                            plan_date=task.end_plan.strftime("%d.%m.%Y"),
                            is_milestone=task.is_milestone,
                            confirm_url=f"{_APP_URL}/smr/confirm/{token}",
                            reject_url=f"{_APP_URL}/smr/confirm/{token}?action=reject",
                        )

                    task.notified_date = today

                db.commit()
                if tasks:
                    logger.warning("smr_notification_loop: отправлено уведомлений по %d задачам", len(tasks))
            except Exception as e:
                db.rollback()
                logger.warning("smr_notification_loop error: %s", e)
            finally:
                db.close()
        except Exception as e:
            logger.warning("smr_notification_loop outer error: %s", e)


# ─── Дайджест руководителя ────────────────────────────────────────────────────

async def leader_digest_loop():
    """
    Ежедневно в ~09:00 МСК отправляет дайджест всем is_admin-пользователям.
    Активируется только при LEADER_DIGEST_ENABLED=true.
    Пока переменная не задана — цикл работает вхолостую, письма НЕ отправляются.
    """
    from datetime import date as _date, datetime as _dt, timedelta as _td
    from services.email_service import send_leader_digest
    from sqlalchemy.orm import joinedload as _jl
    from sqlalchemy import func as _func

    _APP_URL = os.getenv("APP_URL", "https://lenta-web-production.up.railway.app").rstrip("/")

    while True:
        # Ждём до ближайшего 06:00 UTC (= 09:00 МСК)
        now = _dt.utcnow()
        target = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now >= target:
            target += _td(days=1)
        await asyncio.sleep((target - now).total_seconds())

        # Флаг проверяется при каждом срабатывании — включается без рестарта
        if os.getenv("LEADER_DIGEST_ENABLED", "").lower() != "true":
            logger.info("leader_digest_loop: LEADER_DIGEST_ENABLED не задан, пропуск")
            continue

        try:
            today = _date.today()
            db = database.SessionLocal()
            try:
                admins = db.query(models.User).filter(models.User.is_admin == True).all()
                vpk_total = db.query(models.VpkReport).count()

                smr_tasks_today = db.query(models.SmrTask).options(
                    _jl(models.SmrTask.schedule).joinedload(models.SmrSchedule.project)
                ).filter(
                    models.SmrTask.end_plan == today,
                    models.SmrTask.status != "Выполнено"
                ).all()
                smr_list = [
                    {
                        "name": t.name,
                        "project": t.schedule.project.name if t.schedule and t.schedule.project else "",
                        "tk": t.schedule.project.tk_number if t.schedule and t.schedule.project else "",
                        "is_milestone": t.is_milestone,
                    }
                    for t in smr_tasks_today
                ]

                overdue_rows = db.query(
                    models.Manager.name,
                    _func.count(models.Task.id).label("cnt")
                ).join(models.Task, models.Task.assignee_id == models.Manager.id).filter(
                    models.Task.deadline < today,
                    models.Task.status != "Завершена"
                ).group_by(models.Manager.name).all()
                mgr_list = [{"name": r.name, "count": r.cnt} for r in overdue_rows]

                proj_rows = db.query(models.Project).options(
                    _jl(models.Project.manager)
                ).filter(
                    models.Project.opening_date >= today,
                    models.Project.opening_date <= today + _td(days=30),
                    models.Project.status == "Активный"
                ).order_by(models.Project.opening_date).limit(5).all()
                proj_list = [
                    {
                        "name": p.name,
                        "opening_date": p.opening_date.strftime("%d.%m.%Y"),
                        "days": (p.opening_date - today).days,
                        "manager": p.manager.name if p.manager else "",
                    }
                    for p in proj_rows
                ]

                for admin in admins:
                    read_count = db.query(models.VpkReportRead).filter(
                        models.VpkReportRead.reader_name == (admin.display_name or admin.username)
                    ).count()
                    vpk_unread = max(0, vpk_total - read_count)

                    mgr = db.query(models.Manager).filter(
                        models.Manager.name.ilike(f"%{(admin.display_name or '').split()[0]}%")
                    ).first()
                    to_email = mgr.email if mgr and mgr.email else ""
                    if not to_email:
                        logger.info("leader_digest: нет email для %s, пропуск", admin.display_name)
                        continue

                    send_leader_digest(
                        to_email=to_email,
                        name=admin.display_name or admin.username,
                        vpk_unread=vpk_unread,
                        smr_today=smr_list,
                        overdue_managers=mgr_list,
                        critical_projects=proj_list,
                        app_url=_APP_URL,
                    )
                    logger.warning("leader_digest: отправлен → %s (%s)", admin.display_name, to_email)

            except Exception as e:
                logger.warning("leader_digest_loop inner error: %s", e)
            finally:
                db.close()
        except Exception as e:
            logger.warning("leader_digest_loop outer error: %s", e)


# ─── Startup ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    models.Base.metadata.create_all(bind=database.engine)

    if "postgresql" in str(database.DATABASE_URL):
        try:
            with database.engine.begin() as conn:
                for sql in [
                    "ALTER TABLE projects ALTER COLUMN city TYPE TEXT",
                    "ALTER TABLE projects ALTER COLUMN stage TYPE TEXT",
                    "ALTER TABLE project_stages ALTER COLUMN name TYPE TEXT",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS format_type VARCHAR(50) DEFAULT ''",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS open_status VARCHAR(100) DEFAULT ''",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS delay_reason TEXT DEFAULT ''",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
                    "ALTER TABLE managers ADD COLUMN IF NOT EXISTS photo VARCHAR(200) DEFAULT ''",
                    "ALTER TABLE managers ADD COLUMN IF NOT EXISTS position VARCHAR(150) DEFAULT ''",
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completion_comment TEXT DEFAULT ''",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER DEFAULT 1",
                    """CREATE TABLE IF NOT EXISTS task_notifications (
                        id SERIAL PRIMARY KEY,
                        recipient_name VARCHAR(100) NOT NULL,
                        task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                        message TEXT NOT NULL,
                        is_read BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW()
                    )""",
                    "ALTER TABLE vpk_report_items ADD COLUMN IF NOT EXISTS comment TEXT DEFAULT ''",
                    "ALTER TABLE vpk_report_items ADD COLUMN IF NOT EXISTS photo_path VARCHAR(300) DEFAULT ''",
                    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS photo_path VARCHAR(300) DEFAULT ''",
                    "CREATE TABLE IF NOT EXISTS ai_chat_messages (id SERIAL PRIMARY KEY, user_name VARCHAR(100) NOT NULL, role VARCHAR(20) NOT NULL, text TEXT NOT NULL, provider VARCHAR(30) DEFAULT 'groq', created_at TIMESTAMP DEFAULT NOW())",
                    """CREATE TABLE IF NOT EXISTS webauthn_credentials (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
                        credential_id TEXT UNIQUE NOT NULL,
                        public_key TEXT NOT NULL,
                        sign_count INTEGER DEFAULT 0,
                        device_name VARCHAR(150) DEFAULT '',
                        created_at TIMESTAMP DEFAULT NOW()
                    )""",
                    """CREATE TABLE IF NOT EXISTS vpk_report_reads (
                        id SERIAL PRIMARY KEY,
                        report_id INTEGER REFERENCES vpk_reports(id) ON DELETE CASCADE NOT NULL,
                        reader_name VARCHAR(100) NOT NULL,
                        read_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(report_id, reader_name)
                    )""",
                    """CREATE TABLE IF NOT EXISTS task_photos (
                        id SERIAL PRIMARY KEY,
                        task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE NOT NULL,
                        photo_path VARCHAR(300) NOT NULL,
                        uploaded_by VARCHAR(100) DEFAULT '',
                        uploaded_at TIMESTAMP DEFAULT NOW()
                    )""",
                    "CREATE INDEX IF NOT EXISTS ix_chat_sender_name ON chat_messages (sender_name)",
                    "CREATE INDEX IF NOT EXISTS ix_vpk_report_submitted_at ON vpk_reports (submitted_at)",
                    "CREATE INDEX IF NOT EXISTS ix_ai_chat_user_name ON ai_chat_messages (user_name)",
                    "ALTER TABLE smr_tasks ADD COLUMN IF NOT EXISTS notified_date DATE",
                    "ALTER TABLE smr_tasks ADD COLUMN IF NOT EXISTS reject_comment TEXT DEFAULT ''",
                    """CREATE TABLE IF NOT EXISTS smr_contacts (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        email VARCHAR(200) NOT NULL,
                        position VARCHAR(150) DEFAULT '',
                        created_at TIMESTAMP DEFAULT NOW()
                    )""",
                    """CREATE TABLE IF NOT EXISTS smr_schedules (
                        id SERIAL PRIMARY KEY,
                        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )""",
                    """CREATE TABLE IF NOT EXISTS smr_tasks (
                        id SERIAL PRIMARY KEY,
                        schedule_id INTEGER REFERENCES smr_schedules(id) ON DELETE CASCADE NOT NULL,
                        name TEXT NOT NULL,
                        "order" INTEGER DEFAULT 0,
                        start_plan DATE,
                        end_plan DATE,
                        is_milestone BOOLEAN DEFAULT FALSE,
                        status VARCHAR(30) DEFAULT 'Запланировано',
                        notify_email1 VARCHAR(200) DEFAULT '',
                        notify_email2 VARCHAR(200) DEFAULT ''
                    )""",
                    """CREATE TABLE IF NOT EXISTS smr_confirmations (
                        id SERIAL PRIMARY KEY,
                        task_id INTEGER REFERENCES smr_tasks(id) ON DELETE CASCADE NOT NULL,
                        token VARCHAR(64) UNIQUE NOT NULL,
                        email VARCHAR(200) DEFAULT '',
                        action VARCHAR(20) DEFAULT '',
                        responded_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW()
                    )""",
                    """CREATE TABLE IF NOT EXISTS audit_logs (
                        id SERIAL PRIMARY KEY,
                        user_name  VARCHAR(100) DEFAULT '',
                        user_phone VARCHAR(20)  DEFAULT '',
                        path       VARCHAR(300) DEFAULT '',
                        method     VARCHAR(10)  DEFAULT 'GET',
                        ip         VARCHAR(50)  DEFAULT '',
                        created_at TIMESTAMP DEFAULT NOW()
                    )""",
                ]:
                    try:
                        conn.exec_driver_sql(sql)
                    except Exception as e:
                        logger.debug("startup migration skipped: %s", e)
        except Exception as e:
            logger.warning("startup: could not run migrations: %s", e)

    # SQLite-миграции для локальной разработки (добавляем колонки к существующим таблицам)
    if "sqlite" in str(database.DATABASE_URL):
        try:
            with database.engine.begin() as conn:
                for sql in [
                    "ALTER TABLE managers ADD COLUMN photo VARCHAR(200) DEFAULT ''",
                    "ALTER TABLE managers ADD COLUMN position VARCHAR(150) DEFAULT ''",
                    "ALTER TABLE projects ADD COLUMN format_type VARCHAR(50) DEFAULT ''",
                    "ALTER TABLE projects ADD COLUMN open_status VARCHAR(100) DEFAULT ''",
                    "ALTER TABLE projects ADD COLUMN delay_reason TEXT DEFAULT ''",
                    "ALTER TABLE projects ADD COLUMN updated_at TIMESTAMP",
                    "ALTER TABLE tasks ADD COLUMN completion_comment TEXT DEFAULT ''",
                    "ALTER TABLE vpk_report_items ADD COLUMN comment TEXT DEFAULT ''",
                    "ALTER TABLE vpk_report_items ADD COLUMN photo_path VARCHAR(300) DEFAULT ''",
                    "ALTER TABLE chat_messages ADD COLUMN photo_path VARCHAR(300) DEFAULT ''",
                    """CREATE TABLE IF NOT EXISTS vpk_report_reads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        report_id INTEGER NOT NULL,
                        reader_name VARCHAR(100) NOT NULL,
                        read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(report_id, reader_name)
                    )""",
                    """CREATE TABLE IF NOT EXISTS task_photos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER NOT NULL,
                        photo_path VARCHAR(300) NOT NULL,
                        uploaded_by VARCHAR(100) DEFAULT '',
                        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )""",
                    "CREATE INDEX IF NOT EXISTS ix_chat_sender_name ON chat_messages (sender_name)",
                    "CREATE INDEX IF NOT EXISTS ix_vpk_report_submitted_at ON vpk_reports (submitted_at)",
                    "CREATE INDEX IF NOT EXISTS ix_ai_chat_user_name ON ai_chat_messages (user_name)",
                ]:
                    try:
                        conn.exec_driver_sql(sql)
                    except Exception:
                        pass  # уже существует
        except Exception as e:
            logger.warning("startup: SQLite migration error: %s", e)

    db = database.SessionLocal()
    try:
        # Добавляем менеджеров из MANAGERS_SEED если их нет (upsert по имени)
        existing_names = {m.name for m in db.query(models.Manager).all()}
        for name, is_leader in MANAGERS_SEED:
            if name not in existing_names:
                db.add(models.Manager(name=name, is_leader=is_leader))
        db.commit()

        # Прописать фотографии, должности и email менеджерам
        MANAGER_DEFAULTS = {
            "Гаврин Игорь":       {"photo": "img/managers/gavrin.png",  "position": "Руководитель проектов",                        "email": "igor.gavrin@lenta.com"},
            "Комаров Алексей":    {"photo": "img/managers/komarov.png", "position": "Директор по эксплуатации и реконструкции"},
            "Месмер Денис":       {"photo": "img/raccoon_mesmer.jpg",   "position": "Менеджер проектов",                             "email": "denis.mesmer@lenta.com"},
            "Митько Роберт":      {"email": "robert.mitko@lenta.com"},
            "Ловчиков Александр": {"email": "alexander.lovchikov@lenta.com"},
            "Валеев Борис":       {"email": "boris.valeev@lenta.com"},
            "Студеникин Сергей":  {"email": "sergey.studenikin@lenta.com"},
            "Косило Сергей":      {"email": "sergey.kosilo@lenta.com"},
            "Хачатурова Жанна":   {"email": "zhanna.hachaturova@lenta.com"},
            "Шевченко Наталья":   {"email": "nataiya.shevchenko@lenta.com"},
        }
        _DEFAULT_POSITION = "Менеджер проектов"
        for mgr in db.query(models.Manager).all():
            defaults = MANAGER_DEFAULTS.get(mgr.name, {})
            if defaults.get("photo") and not mgr.photo:
                mgr.photo = defaults["photo"]
            pos = defaults.get("position", _DEFAULT_POSITION)
            if not mgr.position:
                mgr.position = pos
            if defaults.get("email") and not mgr.email:
                mgr.email = defaults["email"]
        db.commit()

        # Прописать email и права менеджерам из переменных окружения
        # MANAGER_EMAIL_Имя_Фамилия=email  |  MANAGER_LEADER_Имя_Фамилия=true/false
        for mgr in db.query(models.Manager).all():
            key = mgr.name.replace(" ", "_")
            email_val = os.getenv(f"MANAGER_EMAIL_{key}", "").strip().lower()
            if email_val and mgr.email != email_val:
                mgr.email = email_val
            leader_val = os.getenv(f"MANAGER_LEADER_{key}", "").strip().lower()
            if leader_val in ("true", "1", "yes"):
                mgr.is_leader = True
            elif leader_val in ("false", "0", "no"):
                mgr.is_leader = False
        db.commit()

        # Первый администратор — из переменной окружения ADMIN_PHONE
        # Для тестирования: установить ADMIN_PHONE в .env или Railway Variables
        admin_phone = os.getenv("ADMIN_PHONE", "")
        admin_name  = os.getenv("ADMIN_NAME", "Администратор")
        if admin_phone and db.query(models.PhoneWhitelist).count() == 0:
            db.add(models.PhoneWhitelist(
                phone=admin_phone, display_name=admin_name, is_admin=True))
            db.commit()

        # Дополнительные пользователи при первом запуске.
        # Формат в переменной SEED_USERS (опционально):
        #   +79001112233:Иванов Иван:false,+79003334455:Петров Пётр:true
        seed_users_env = os.getenv("SEED_USERS", "")
        if seed_users_env:
            for entry in seed_users_env.split(","):
                parts = entry.strip().split(":")
                if len(parts) >= 2:
                    ph, nm = parts[0].strip(), parts[1].strip()
                    adm = len(parts) >= 3 and parts[2].strip().lower() == "true"
                    if not db.query(models.PhoneWhitelist).filter(
                            models.PhoneWhitelist.phone == ph).first():
                        db.add(models.PhoneWhitelist(
                            phone=ph, display_name=nm, is_admin=adm))
            db.commit()

        if db.query(models.VpkCriterion).count() == 0:
            vpk1 = [
                "Документация на произведённые работы предоставлена в полном объёме в печатном виде, согласно технического задания.",
                "Температурный режим на объекте обеспечивается, согласно условий технического задания с учётом времени года.",
                "Подъёмное оборудование для перегрузки товара смонтировано и введено в эксплуатацию.",
                "Холодильное оборудование запущено и выведено в режим, функционирует без аварий более 24 часов.",
                "Строительство подъездных путей окончено, препятствий для подъезда к зоне разгрузки нет.",
                "Системы пожарной безопасности смонтированы, находятся в исправном и автоматическом режиме, готовы к проведению комплексных испытаний.",
                "Электроснабжение объекта осуществляется по постоянной схеме подключения.",
                "Объект обеспечен всеми необходимыми коммунальными ресурсами, согласно условий договора аренды.",
                "Периметр объекта замкнут, все двери/ворота установлены, исправны.",
                "Лотки и кабельные трассы системы видеонаблюдения смонтированы, проводятся пуско-наладочные работы.",
                "Объект обеспечен доступом в интернет (один канал), зона приёмки товара оборудована всем необходимым, препятствий для приёма товара нет.",
                "Основные строительно-монтажные работы закончены.",
                "Лотки и кабельные трассы системы охранной сигнализации смонтированы, проводятся пуско-наладочные работы.",
                "Охрана объекта обеспечена сотрудником ЧОП.",
                "ДДА с распределением зон эксплуатационной ответственности предоставлен.",
                "Согласование контейнерной площадки со стороны местной администрации предоставлено от АРДД.",
                "Укомплектованность собственным персоналом не ниже 60%.",
            ]
            vpk2 = [
                "Технологическое оборудование полностью смонтировано и запущено.",
                "Системы пожарной безопасности находятся в полностью исправном состоянии, все неисправности устранены или признаны инженером ПБ не значительными и не влияющими на общую работоспособность системы.",
                "Рекламная вывеска смонтирована, в ночное время светится.",
                "Всё кассовое оборудование запущено и исправно, все IT коммуникации смонтированы, исправны.",
                "Входная группа готова для открытия объекта, наружные работы и благоустройство завершены.",
                "Охранная сигнализация смонтирована, исправна.",
                "Система видеонаблюдения смонтирована, исправна.",
                "Уличное освещение объекта смонтировано, исправно.",
                "Маркетинговое оформление СМ полностью закончено.",
                "Строительство парковки для клиентов (при наличии) окончено, препятствий для размещения автомобилей нет.",
                "Укомплектованность собственным персоналом не ниже 70%.",
                "Объект обеспечен доступом в интернет (два канала передачи данных).",
                "В зоне кассовой линейки должен быть обеспечен устойчивый сигнал сотовой связи (мобильное приложение ЛЕНТА запускается, существует возможность оплаты по СБП с личного мобильного телефона покупателя).",
            ]
            for i, name in enumerate(vpk1):
                db.add(models.VpkCriterion(vpk_type=1, name=name, order=i))
            for i, name in enumerate(vpk2):
                db.add(models.VpkCriterion(vpk_type=2, name=name, order=i))
            db.commit()
    finally:
        db.close()

    asyncio.create_task(auto_sync_loop())
    asyncio.create_task(smr_notification_loop())
    asyncio.create_task(leader_digest_loop())
