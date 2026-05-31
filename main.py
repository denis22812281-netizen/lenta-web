import asyncio
import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

import database
import models
from config import MANAGERS_SEED
from deps import limiter
from services.excel_import import import_reconstruct_excel, import_construction_excel, parse_excel_file
from services.online import ONLINE_USERS

logger = logging.getLogger(__name__)

app = FastAPI(title="Лента — Управление проектами")


class CSRFMiddleware(BaseHTTPMiddleware):
    """Проверяет CSRF-токен для всех POST-форм (кроме API и логина)."""
    _EXEMPT = ("/api/", "/login/")
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

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.add_middleware(CSRFMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400 * 7,
                   same_site="lax", https_only=bool(os.getenv("RAILWAY_ENVIRONMENT")))
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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

for r in [auth_router, webauthn_router, dashboard_router, projects_router, sections_router,
          kso_router, tasks_router, managers_router, deadlines_router,
          vpk_router, stats_router, admin_router, chat_router,
          ai_router, api_router, sync_router]:
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
                        path = Path(cfg.file_path)
                        if path.exists() and path.suffix in ('.xlsx', '.xls', '.xlsm'):
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
                    """CREATE TABLE IF NOT EXISTS task_notifications (
                        id SERIAL PRIMARY KEY,
                        recipient_name VARCHAR(100) NOT NULL,
                        task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
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
                ]:
                    try:
                        conn.exec_driver_sql(sql)
                    except Exception as e:
                        logger.debug("startup migration skipped: %s", e)
        except Exception as e:
            logger.warning("startup: could not run migrations: %s", e)

    db = database.SessionLocal()
    try:
        if db.query(models.Manager).count() == 0:
            for name, is_leader in MANAGERS_SEED:
                db.add(models.Manager(name=name, is_leader=is_leader))
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
