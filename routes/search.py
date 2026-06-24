from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import require_login, templates

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = "",
    manager_id: str = "",
    date_from: str = "",
    date_to: str = "",
    project_type: str = "",
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    results = {"projects": [], "managers": [], "tasks": []}
    has_filters = bool(q.strip() or manager_id or date_from or date_to or project_type)

    if has_filters:
        like = f"%{q.strip()}%" if q.strip() else "%"

        # ── Проекты ──────────────────────────────────────────────
        pq = db.query(models.Project)
        if q.strip():
            pq = pq.filter(
                models.Project.tk_number.ilike(like) |
                models.Project.name.ilike(like) |
                models.Project.city.ilike(like) |
                models.Project.address.ilike(like)
            )
        if manager_id and manager_id.isdigit():
            pq = pq.filter(models.Project.manager_id == int(manager_id))
        if project_type:
            pq = pq.filter(models.Project.project_type == project_type)
        if date_from:
            try:
                df = datetime.strptime(date_from, "%Y-%m-%d").date()
                pq = pq.filter(models.Project.end_date >= df)
            except ValueError:
                pass
        if date_to:
            try:
                dt = datetime.strptime(date_to, "%Y-%m-%d").date()
                pq = pq.filter(models.Project.end_date <= dt)
            except ValueError:
                pass
        results["projects"] = pq.order_by(models.Project.end_date.nullslast()).limit(30).all()

        # ── Менеджеры (только по текстовому запросу) ─────────────
        if q.strip():
            results["managers"] = (
                db.query(models.Manager)
                .filter(models.Manager.name.ilike(like))
                .limit(10).all()
            )

        # ── Задачи ────────────────────────────────────────────────
        tq = db.query(models.Task)
        if q.strip():
            tq = tq.filter(models.Task.title.ilike(like))
        if date_from:
            try:
                df = datetime.strptime(date_from, "%Y-%m-%d").date()
                tq = tq.filter(models.Task.deadline >= df)
            except ValueError:
                pass
        if date_to:
            try:
                dt = datetime.strptime(date_to, "%Y-%m-%d").date()
                tq = tq.filter(models.Task.deadline <= dt)
            except ValueError:
                pass
        results["tasks"] = tq.order_by(models.Task.deadline.nullslast()).limit(15).all()

    total = sum(len(v) for v in results.values())
    managers_list = db.query(models.Manager).order_by(models.Manager.name).all()

    return templates.TemplateResponse("search.html", {
        "request": request, "user": user,
        "q": q, "results": results, "total": total, "today": date.today(),
        "filter_manager_id": manager_id,
        "filter_date_from": date_from,
        "filter_date_to": date_to,
        "filter_type": project_type,
        "managers_list": managers_list,
        "has_filters": has_filters,
        "project_types": ["Реконструкция", "Констракшн"],
    })
