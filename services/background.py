import asyncio
import logging
import os
import secrets as _sec
from datetime import date as _date
from datetime import datetime
from datetime import timedelta as _td
from pathlib import Path

import database
import models
from services.email_service import send_leader_digest, send_smr_deadline_notification
from services.excel_import import (
    import_construction_excel,
    import_reconstruct_excel,
    parse_excel_file,
)

logger = logging.getLogger(__name__)

_APP_URL = os.getenv("APP_URL", "https://lenta-web-production.up.railway.app").rstrip("/")


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
                        _blocked = ('/etc', '/proc', '/sys', '/root', '/var/run',
                                    'C:\\Windows', 'C:\\System32', 'C:\\Program Files')
                        _safe = (path.exists()
                                 and path.suffix in ('.xlsx', '.xls', '.xlsm')
                                 and not any(str(path).startswith(b) for b in _blocked)
                                 and path.stat().st_size < 50 * 1024 * 1024)
                        if _safe:
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


async def smr_notification_loop():
    while True:
        await asyncio.sleep(3600)
        try:
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
                        token = _sec.token_hex(32)
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


async def leader_digest_loop():
    from sqlalchemy import func as _func
    from sqlalchemy.orm import joinedload as _jl

    while True:
        now = datetime.utcnow()
        target = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now >= target:
            target += _td(days=1)
        await asyncio.sleep((target - now).total_seconds())

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
