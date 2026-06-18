from datetime import date, timedelta
from collections import defaultdict

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from deps import templates, require_login
from services.cache import cache_get, cache_set

router = APIRouter()

_STATS_TTL = 180  # 3 минуты


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db),
                    user: dict = Depends(require_login)):
    today = date.today()
    cache_key = f"dashboard:stats:{today.isoformat()}"

    stats = await cache_get(cache_key)
    if stats is None:
        total_projects  = db.query(models.Project).count()
        active_projects = db.query(models.Project).filter(
            models.Project.status == "Активный").count()
        overdue_tasks = db.query(models.Task).filter(
            models.Task.deadline < today, models.Task.status != "Завершена").count()
        tasks_due_soon = db.query(models.Task).filter(
            models.Task.deadline >= today,
            models.Task.deadline <= today + timedelta(days=7),
            models.Task.status != "Завершена").count()

        proj_by_status = {
            row.status: row.cnt
            for row in db.query(
                models.Project.status,
                func.count(models.Project.id).label("cnt")
            ).group_by(models.Project.status).all()
        }
        proj_by_type = {
            row.project_type: row.cnt
            for row in db.query(
                models.Project.project_type,
                func.count(models.Project.id).label("cnt")
            ).filter(models.Project.project_type != "").group_by(models.Project.project_type).all()
        }
        task_by_status = {
            row.status: row.cnt
            for row in db.query(
                models.Task.status,
                func.count(models.Task.id).label("cnt")
            ).group_by(models.Task.status).all()
        }
        tasks_per_mgr = [
            [row[0], row[1]]
            for row in db.query(
                models.Manager.name,
                func.count(models.Task.id).label("cnt")
            ).join(models.Task, models.Task.assignee_id == models.Manager.id)
             .group_by(models.Manager.name)
             .order_by(func.count(models.Task.id).desc())
             .limit(8).all()
        ]

        # Calendar heatmap: плотность дедлайнов по дням (следующие 90 дней)
        heatmap: dict[str, int] = defaultdict(int)
        end_range = today + timedelta(days=90)
        for t in db.query(models.Task.deadline).filter(
            models.Task.deadline >= today,
            models.Task.deadline <= end_range,
            models.Task.status != "Завершена",
        ).all():
            if t.deadline:
                heatmap[t.deadline.isoformat()] += 1
        for p in db.query(models.Project.end_date).filter(
            models.Project.end_date >= today,
            models.Project.end_date <= end_range,
            models.Project.status == "Активный",
        ).all():
            if p.end_date:
                heatmap[p.end_date.isoformat()] += 2  # проекты весят больше

        deadline_heatmap = [[k, v] for k, v in sorted(heatmap.items())]

        stats = {
            "total_projects": total_projects,
            "active_projects": active_projects,
            "overdue_tasks": overdue_tasks,
            "tasks_due_soon": tasks_due_soon,
            "proj_by_status": proj_by_status,
            "proj_by_type": proj_by_type,
            "task_by_status": task_by_status,
            "tasks_per_mgr": tasks_per_mgr,
            "deadline_heatmap": deadline_heatmap,
            "heatmap_range": [today.isoformat(), end_range.isoformat()],
        }
        await cache_set(cache_key, stats, ttl=_STATS_TTL)

    # Живые данные — не кешируем (должны быть актуальны)
    projects_deadline_soon = db.query(models.Project).options(
        joinedload(models.Project.manager)
    ).filter(
        models.Project.end_date >= today,
        models.Project.end_date <= today + timedelta(days=14),
        models.Project.status == "Активный",
        models.Project.project_type == "Констракшн",
        (models.Project.opening_date == None) | (models.Project.opening_date > today)
    ).order_by(models.Project.end_date).limit(6).all()
    recent_tasks = db.query(models.Task).options(
        joinedload(models.Task.assignee)
    ).order_by(models.Task.created_at.desc()).limit(6).all()

    return templates.TemplateResponse("index.html", {
        "request": request, "user": user,
        "total_projects": stats["total_projects"],
        "active_projects": stats["active_projects"],
        "overdue_tasks": stats["overdue_tasks"],
        "tasks_due_soon": stats["tasks_due_soon"],
        "projects_deadline_soon": projects_deadline_soon,
        "recent_tasks": recent_tasks, "today": today,
        "proj_by_status": stats["proj_by_status"],
        "proj_by_type": stats["proj_by_type"],
        "task_by_status": stats["task_by_status"],
        "tasks_per_mgr": stats["tasks_per_mgr"],
        "deadline_heatmap": stats.get("deadline_heatmap", []),
        "heatmap_range": stats.get("heatmap_range", [today.isoformat(), (today + timedelta(days=90)).isoformat()]),
    })
