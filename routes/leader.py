from datetime import date, timedelta

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from deps import templates, require_admin

router = APIRouter()


@router.get("/leader", response_class=HTMLResponse)
async def leader_dashboard(request: Request, db: Session = Depends(get_db),
                           user: dict = Depends(require_admin)):
    today = date.today()
    tomorrow = today + timedelta(days=1)
    week_ahead = today + timedelta(days=7)
    month_ahead = today + timedelta(days=30)

    user_name = user.get("display_name", "")

    # ── ВПК непрочитанные ────────────────────────────────────────────────────
    total_vpk = db.query(models.VpkReport).count()
    read_by_me = db.query(models.VpkReportRead).filter(
        models.VpkReportRead.reader_name == user_name).count()
    vpk_unread = max(0, total_vpk - read_by_me)
    vpk_latest = db.query(models.VpkReport).options(
        joinedload(models.VpkReport.project)
    ).order_by(models.VpkReport.submitted_at.desc()).limit(5).all()

    # ── СМР дедлайны ─────────────────────────────────────────────────────────
    smr_today = db.query(models.SmrTask).options(
        joinedload(models.SmrTask.schedule).joinedload(models.SmrSchedule.project)
    ).filter(
        models.SmrTask.end_plan == today,
        models.SmrTask.status != "Выполнено"
    ).all()

    smr_tomorrow = db.query(models.SmrTask).options(
        joinedload(models.SmrTask.schedule).joinedload(models.SmrSchedule.project)
    ).filter(
        models.SmrTask.end_plan == tomorrow,
        models.SmrTask.status != "Выполнено"
    ).all()

    smr_week_count = db.query(models.SmrTask).filter(
        models.SmrTask.end_plan > tomorrow,
        models.SmrTask.end_plan <= week_ahead,
        models.SmrTask.status != "Выполнено"
    ).count()

    # ── Менеджеры с просроченными задачами ───────────────────────────────────
    overdue_by_manager = db.query(
        models.Manager.id,
        models.Manager.name,
        models.Manager.photo,
        func.count(models.Task.id).label("overdue_count")
    ).join(models.Task, models.Task.assignee_id == models.Manager.id).filter(
        models.Task.deadline < today,
        models.Task.status != "Завершена"
    ).group_by(
        models.Manager.id, models.Manager.name, models.Manager.photo
    ).order_by(func.count(models.Task.id).desc()).all()

    # ── Критичные проекты (открытие в ближайшие 30 дней) ─────────────────────
    critical_projects = db.query(models.Project).options(
        joinedload(models.Project.manager)
    ).filter(
        models.Project.opening_date >= today,
        models.Project.opening_date <= month_ahead,
        models.Project.status == "Активный"
    ).order_by(models.Project.opening_date).limit(5).all()

    # ── Задачи созданные мной ─────────────────────────────────────────────────
    my_tasks_open = db.query(models.Task).filter(
        models.Task.created_by == user_name,
        models.Task.status != "Завершена"
    ).count()
    my_tasks_overdue = db.query(models.Task).filter(
        models.Task.created_by == user_name,
        models.Task.status != "Завершена",
        models.Task.deadline < today
    ).count()
    my_recent_tasks = db.query(models.Task).options(
        joinedload(models.Task.assignee),
        joinedload(models.Task.project)
    ).filter(
        models.Task.created_by == user_name
    ).order_by(models.Task.created_at.desc()).limit(8).all()

    # ── Сводные счётчики ──────────────────────────────────────────────────────
    total_overdue_tasks = db.query(models.Task).filter(
        models.Task.deadline < today,
        models.Task.status != "Завершена"
    ).count()

    active_projects = db.query(models.Project).filter(
        models.Project.status == "Активный"
    ).count()

    week_end = today + timedelta(days=(6 - today.weekday()))
    opens_this_week = db.query(models.Project).filter(
        models.Project.end_date >= today,
        models.Project.end_date <= week_end,
        models.Project.status == "Активный"
    ).count()

    return templates.TemplateResponse("leader.html", {
        "request": request, "user": user,
        "today": today,
        "vpk_unread": vpk_unread,
        "vpk_latest": vpk_latest,
        "smr_today": smr_today,
        "smr_tomorrow": smr_tomorrow,
        "smr_week_count": smr_week_count,
        "overdue_by_manager": overdue_by_manager,
        "critical_projects": critical_projects,
        "my_tasks_open": my_tasks_open,
        "my_tasks_overdue": my_tasks_overdue,
        "my_recent_tasks": my_recent_tasks,
        "total_overdue_tasks": total_overdue_tasks,
        "active_projects": active_projects,
        "opens_this_week": opens_this_week,
    })
