"""Исполнительный дашборд — для директора и руководителей (is_admin или is_leader)."""
from datetime import date, timedelta
from calendar import month_abbr

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, case, extract
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from deps import templates, require_executive

router = APIRouter()


@router.get("/executive", response_class=HTMLResponse)
async def executive_dashboard(request: Request, db: Session = Depends(get_db),
                              user: dict = Depends(require_executive)):
    today = date.today()
    year_start = date(today.year, 1, 1)
    quarter_end = today + timedelta(days=90)

    # ── KPI ──────────────────────────────────────────────────────────────────
    opened_this_year = db.query(models.Project).filter(
        models.Project.opening_date >= year_start,
        models.Project.opening_date <= today,
        models.Project.project_type == "Констракшн",
    ).count()

    active_count = db.query(models.Project).filter(
        models.Project.status == "Активный",
        models.Project.project_type == "Констракшн",
    ).count()

    delayed_count = db.query(models.Project).filter(
        models.Project.project_type == "Констракшн",
        models.Project.opening_date >= year_start,
        models.Project.opening_date <= today,
        models.Project.end_date.isnot(None),
        models.Project.opening_date > models.Project.end_date,
    ).count()

    forecast_count = db.query(models.Project).filter(
        models.Project.status == "Активный",
        models.Project.project_type == "Констракшн",
        models.Project.end_date >= today,
        models.Project.end_date <= quarter_end,
        (models.Project.opening_date == None) | (models.Project.opening_date > today),
    ).count()

    # ── Рейтинг менеджеров (5 агрегатных запросов вместо 6×N) ──────────────
    managers = db.query(models.Manager).filter(
        models.Manager.is_leader == False
    ).order_by(models.Manager.name).all()

    active_by_mgr = dict(db.query(
        models.Project.manager_id, func.count(models.Project.id)
    ).filter(
        models.Project.status == "Активный",
        models.Project.project_type == "Констракшн",
        models.Project.manager_id.isnot(None),
    ).group_by(models.Project.manager_id).all())

    opened_by_mgr = dict(db.query(
        models.Project.manager_id, func.count(models.Project.id)
    ).filter(
        models.Project.project_type == "Констракшн",
        models.Project.opening_date >= year_start,
        models.Project.opening_date <= today,
        models.Project.manager_id.isnot(None),
    ).group_by(models.Project.manager_id).all())

    delayed_by_mgr = dict(db.query(
        models.Project.manager_id, func.count(models.Project.id)
    ).filter(
        models.Project.project_type == "Констракшн",
        models.Project.opening_date >= year_start,
        models.Project.opening_date <= today,
        models.Project.end_date.isnot(None),
        models.Project.opening_date > models.Project.end_date,
        models.Project.manager_id.isnot(None),
    ).group_by(models.Project.manager_id).all())

    tasks_overdue_by_mgr = dict(db.query(
        models.Task.assignee_id, func.count(models.Task.id)
    ).filter(
        models.Task.status != "Завершена",
        models.Task.deadline < today,
        models.Task.assignee_id.isnot(None),
    ).group_by(models.Task.assignee_id).all())

    tasks_total_by_mgr = dict(db.query(
        models.Task.assignee_id, func.count(models.Task.id)
    ).filter(
        models.Task.deadline.isnot(None),
        models.Task.assignee_id.isnot(None),
    ).group_by(models.Task.assignee_id).all())

    mgr_stats = []
    for m in managers:
        active        = active_by_mgr.get(m.id, 0)
        opened_yr     = opened_by_mgr.get(m.id, 0)
        delayed       = delayed_by_mgr.get(m.id, 0)
        tasks_overdue = tasks_overdue_by_mgr.get(m.id, 0)
        tasks_total   = tasks_total_by_mgr.get(m.id, 0)
        score = opened_yr * 3 - delayed * 5 - tasks_overdue * 2
        mgr_stats.append({
            "id": m.id, "name": m.name, "photo": m.photo or "",
            "active": active, "opened_yr": opened_yr,
            "delayed": delayed, "tasks_overdue": tasks_overdue,
            "tasks_total": tasks_total,
            "score": score,
        })

    mgr_stats.sort(key=lambda x: x["score"], reverse=True)

    # ── Открытия по месяцам (текущий год) ───────────────────────────────────
    monthly = db.query(
        extract("month", models.Project.opening_date).label("month"),
        func.count(models.Project.id).label("cnt"),
    ).filter(
        models.Project.opening_date >= year_start,
        models.Project.opening_date <= today,
        models.Project.project_type == "Констракшн",
    ).group_by("month").all()

    months_data = [0] * 12
    for row in monthly:
        months_data[int(row.month) - 1] = row.cnt

    month_labels = ["Янв","Фев","Мар","Апр","Май","Июн",
                    "Июл","Авг","Сен","Окт","Ноя","Дек"]

    # ── Прогноз — ближайшие 90 дней ─────────────────────────────────────────
    forecast_projects = db.query(models.Project).options(
        joinedload(models.Project.manager)
    ).filter(
        models.Project.status == "Активный",
        models.Project.project_type == "Констракшн",
        models.Project.end_date >= today,
        models.Project.end_date <= quarter_end,
        (models.Project.opening_date == None) | (models.Project.opening_date > today),
    ).order_by(models.Project.end_date).all()

    # ── Просроченные проекты ─────────────────────────────────────────────────
    overdue_projects = db.query(models.Project).options(
        joinedload(models.Project.manager)
    ).filter(
        models.Project.project_type == "Констракшн",
        models.Project.opening_date >= year_start,
        models.Project.opening_date <= today,
        models.Project.end_date.isnot(None),
        models.Project.opening_date > models.Project.end_date,
    ).order_by(models.Project.opening_date.desc()).all()

    return templates.TemplateResponse("executive.html", {
        "request": request, "user": user, "today": today,
        "opened_this_year": opened_this_year,
        "active_count": active_count,
        "delayed_count": delayed_count,
        "forecast_count": forecast_count,
        "mgr_stats": mgr_stats,
        "months_data": months_data,
        "month_labels": month_labels,
        "forecast_projects": forecast_projects,
        "overdue_projects": overdue_projects,
        "year": today.year,
    })
