from datetime import date, timedelta

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from deps import templates, get_current_user

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    today = date.today()
    total_projects  = db.query(models.Project).count()
    active_projects = db.query(models.Project).filter(models.Project.status == "Активный").count()
    overdue_tasks = db.query(models.Task).filter(
        models.Task.deadline < today, models.Task.status != "Завершена").count()
    tasks_due_soon = db.query(models.Task).filter(
        models.Task.deadline >= today,
        models.Task.deadline <= today + timedelta(days=7),
        models.Task.status != "Завершена").count()
    projects_deadline_soon = db.query(models.Project).options(
        joinedload(models.Project.manager)
    ).filter(
        models.Project.end_date >= today,
        models.Project.end_date <= today + timedelta(days=14),
        models.Project.status == "Активный",
        (models.Project.opening_date == None) | (models.Project.opening_date > today)
    ).order_by(models.Project.end_date).limit(6).all()
    recent_tasks = db.query(models.Task).options(
        joinedload(models.Task.assignee)
    ).order_by(models.Task.created_at.desc()).limit(6).all()
    return templates.TemplateResponse("index.html", {
        "request": request, "user": user,
        "total_projects": total_projects, "active_projects": active_projects,
        "overdue_tasks": overdue_tasks, "tasks_due_soon": tasks_due_soon,
        "projects_deadline_soon": projects_deadline_soon,
        "recent_tasks": recent_tasks, "today": today,
    })
