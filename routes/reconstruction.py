"""Страница реконструкций для руководителя: светофор этапов, просрочки, комментарии."""
from datetime import date, datetime

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

import models
from database import get_db
from deps import templates, require_executive

router = APIRouter()

RECON_STAGES = [
    {"key": "sid",     "label": "Сбор ИД",     "end_field": "sid_end"},
    {"key": "zoning",  "label": "Зонирование",  "end_field": "zoning_end"},
    {"key": "mp",      "label": "МП",           "end_field": "mp_end"},
    {"key": "tp",      "label": "ТП",           "end_field": "tp_end"},
    {"key": "viz",     "label": "Визуал",        "end_field": "visualization_end"},
    {"key": "audit",   "label": "Аудит",         "end_field": "audit_end"},
    {"key": "pjf",     "label": "PJF согл.",     "end_field": "pjf_approval_end"},
    {"key": "ds",      "label": "ДС",            "end_field": "ds_signing_date"},
    {"key": "tz",      "label": "ТЗ/Тендеры",   "end_field": "tz_end"},
    {"key": "closure", "label": "Закрытие",      "end_field": "closure_date"},
    {"key": "vpk",     "label": "ВПК1",          "end_field": "vpk_date"},
    {"key": "opening", "label": "Открытие",      "end_field": "opening_date"},
]

TABS = [
    {"key": "all",          "label": "Все"},
    {"key": "Реконструкции 2026",              "label": "Реконструкции 2026"},
    {"key": "Лайт реконструкции 2026",         "label": "Лайт 2026"},
    {"key": "Рисковые объекты 2026 АЛ",        "label": "Рисковые АЛ"},
    {"key": "Рисковые объекты Малая площадь",  "label": "Малая площадь"},
]

WARN_DAYS = 7


def _cell_css(end_date, is_done: bool, today: date) -> str:
    if is_done:
        return "cell-done"
    if not end_date:
        return "cell-empty"
    days = (end_date - today).days
    if days < 0:
        return "cell-over"
    if days <= WARN_DAYS:
        return "cell-warn"
    return "cell-ok"


@router.get("/reconstruction", response_class=HTMLResponse)
async def reconstruction_page(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_executive),
    tab: str = "all",
    manager_id: str = None,
    only_problems: str = None,
):
    today = date.today()

    q = db.query(models.Project).filter(models.Project.project_type == "Реконструкция")
    if tab != "all":
        q = q.filter(models.Project.format_type == tab)
    if manager_id and manager_id.isdigit():
        q = q.filter(models.Project.manager_id == int(manager_id))
    projects = q.order_by(models.Project.opening_date.nullslast()).all()

    # Загрузим все статусы этапов одним запросом
    project_ids = [p.id for p in projects]
    stage_statuses_raw = db.query(models.ReconStageStatus).filter(
        models.ReconStageStatus.project_id.in_(project_ids)
    ).all() if project_ids else []
    done_map = {(s.project_id, s.stage_key): s for s in stage_statuses_raw}

    # Считаем данные для каждого проекта
    projects_data = []
    overdue_items = []

    for p in projects:
        stages_info = []
        has_problem = False
        for s in RECON_STAGES:
            end_val = getattr(p, s["end_field"], None)
            status_rec = done_map.get((p.id, s["key"]))
            is_done = status_rec.is_done if status_rec else False
            css = _cell_css(end_val, is_done, today)
            if css == "cell-over":
                has_problem = True
                overdue_items.append({
                    "tk": p.tk_number,
                    "city": p.city or "",
                    "project_id": p.id,
                    "stage_label": s["label"],
                    "days": (today - end_val).days,
                    "manager": p.manager.name if p.manager else "—",
                    "end_date": end_val,
                })
            stages_info.append({
                "key": s["key"],
                "label": s["label"],
                "end_date": end_val,
                "is_done": is_done,
                "css": css,
            })

        if only_problems and not has_problem:
            continue

        projects_data.append({"project": p, "stages": stages_info})

    # Сортируем просрочки по количеству дней (самые критичные сверху)
    overdue_items.sort(key=lambda x: -x["days"])

    managers = db.query(models.Manager).filter(
        models.Manager.is_leader == False
    ).order_by(models.Manager.name).all()

    return templates.TemplateResponse("reconstruction.html", {
        "request": request, "user": user,
        "projects_data": projects_data,
        "overdue_items": overdue_items,
        "stages": RECON_STAGES,
        "tabs": TABS,
        "active_tab": tab,
        "managers": managers,
        "filter_manager_id": manager_id,
        "only_problems": only_problems,
        "today": today,
        "total": len(projects_data),
    })


class StageToggleIn(BaseModel):
    project_id: int
    stage_key: str
    is_done: bool


@router.post("/api/reconstruction/stage")
async def toggle_stage(
    payload: StageToggleIn,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_executive),
):
    today = date.today()
    rec = db.query(models.ReconStageStatus).filter(
        models.ReconStageStatus.project_id == payload.project_id,
        models.ReconStageStatus.stage_key == payload.stage_key,
    ).first()

    if rec:
        rec.is_done = payload.is_done
        rec.done_by = user.get("display_name", "")
        rec.done_at = datetime.utcnow() if payload.is_done else None
    else:
        rec = models.ReconStageStatus(
            project_id=payload.project_id,
            stage_key=payload.stage_key,
            is_done=payload.is_done,
            done_by=user.get("display_name", ""),
            done_at=datetime.utcnow() if payload.is_done else None,
        )
        db.add(rec)
    db.commit()

    # Вернём новый CSS класс чтобы фронтенд обновил ячейку без перезагрузки
    p = db.query(models.Project).filter(models.Project.id == payload.project_id).first()
    end_val = None
    for s in RECON_STAGES:
        if s["key"] == payload.stage_key:
            end_val = getattr(p, s["end_field"], None)
            break
    css = _cell_css(end_val, payload.is_done, today)

    return JSONResponse({"ok": True, "css": css, "is_done": payload.is_done})
