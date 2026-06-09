from datetime import date

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, require_login

router = APIRouter()


@router.get("/deadlines", response_class=HTMLResponse)
async def deadlines(request: Request, db: Session = Depends(get_db),
                    manager_id: str = None, view: str = "all",
                    user: dict = Depends(require_login)):
    today = date.today()
    pq = db.query(models.Project).filter(
        models.Project.status != "Завершён",
        models.Project.end_date != None,
        models.Project.project_type == "Констракшн",
        (models.Project.opening_date == None) | (models.Project.opening_date > today)
    )
    if manager_id and str(manager_id).isdigit():
        pq = pq.filter(models.Project.manager_id == int(manager_id))
    projects = pq.order_by(models.Project.end_date).all()

    tq = db.query(models.Task).filter(
        models.Task.status != "Завершена", models.Task.deadline != None)
    if manager_id and str(manager_id).isdigit():
        tq = tq.filter(models.Task.assignee_id == int(manager_id))
    tasks = tq.order_by(models.Task.deadline).all()

    managers = db.query(models.Manager).all()
    return templates.TemplateResponse("deadlines.html", {
        "request": request, "user": user,
        "projects": projects, "tasks": tasks,
        "managers": managers, "today": today,
        "filter_manager_id": manager_id, "view": view,
    })
