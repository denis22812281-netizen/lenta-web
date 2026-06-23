from datetime import date

from fastapi import APIRouter, Request, Depends, Query
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
    show_done: bool = Query(False),
    ptype: str = Query(""),
):
    today = date.today()

    q = db.query(models.Project).options(joinedload(models.Project.manager))

    # Тип проекта (фильтр)
    if ptype:
        q = q.filter(models.Project.project_type == ptype)

    # По умолчанию скрываем Завершён — их обычно сотни
    if not show_done:
        q = q.filter(models.Project.status != "Завершён")

    projects = q.all()

    # Авто-проставляем "Просрочен" для активных с истёкшим дедлайном
    for p in projects:
        if (
            p.end_date
            and p.end_date < today
            and p.status in ("Активный", "В работе", "Планирование")
            and not p.opening_date
        ):
            p.status = "Просрочен"
    db.commit()

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

    # Уникальные типы для фильтра
    ptypes = (
        db.query(models.Project.project_type)
        .filter(models.Project.project_type.isnot(None), models.Project.project_type != "")
        .distinct()
        .all()
    )
    project_types = sorted(set(r[0] for r in ptypes))

    total = sum(len(v) for v in columns.values())

    return templates.TemplateResponse("kanban.html", {
        "request": request,
        "user": user,
        "columns": columns,
        "status_color": _STATUS_COLOR,
        "today": today,
        "show_done": show_done,
        "ptype": ptype,
        "project_types": project_types,
        "total": total,
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
