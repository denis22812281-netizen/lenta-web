from datetime import date

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from deps import templates, require_login

router = APIRouter()

_STATUS_ORDER = [
    "Планирование",
    "Активный",
    "В работе",
    "Срочный",
    "Просрочен",
    "Завершён",
]

_STATUS_COLOR = {
    "Планирование": "primary",
    "Активный":     "success",
    "В работе":     "info",
    "Срочный":      "warning",
    "Просрочен":    "danger",
    "Завершён":     "secondary",
}


@router.get("/kanban", response_class=HTMLResponse)
async def kanban_page(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    today = date.today()
    projects = (
        db.query(models.Project)
        .options(joinedload(models.Project.manager))
        .all()
    )

    all_statuses = set(p.status for p in projects if p.status)
    ordered = [s for s in _STATUS_ORDER if s in all_statuses]
    for s in sorted(all_statuses - set(_STATUS_ORDER)):
        ordered.append(s)

    columns: dict[str, list] = {s: [] for s in ordered}
    for p in projects:
        s = p.status or "Активный"
        if s not in columns:
            columns[s] = []
        columns[s].append(p)

    return templates.TemplateResponse("kanban.html", {
        "request": request,
        "user": user,
        "columns": columns,
        "status_color": _STATUS_COLOR,
        "today": today,
    })


@router.post("/api/kanban/move")
async def kanban_move(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    data = await request.json()
    project_id = int(data.get("id", 0))
    new_status = str(data.get("status", "")).strip()
    if not project_id or not new_status:
        return JSONResponse({"ok": False})

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        return JSONResponse({"ok": False})

    old_status = project.status or ""
    if old_status == new_status:
        return JSONResponse({"ok": True})

    project.status = new_status
    db.add(models.ProjectHistory(
        project_id=project.id,
        changed_by=user.get("display_name", ""),
        field_label="Статус",
        old_value=old_status,
        new_value=new_status,
    ))
    db.commit()
    return JSONResponse({"ok": True})
