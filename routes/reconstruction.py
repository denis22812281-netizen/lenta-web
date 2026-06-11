"""Центр управления реконструкциями: светофор этапов, риски, аналитика."""
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
    {"key": "sid",     "label": "Сбор ИД",   "short": "ИД",  "start_field": "sid_start",           "end_field": "sid_end"},
    {"key": "zoning",  "label": "Зонирование","short": "Зон", "start_field": "zoning_start",        "end_field": "zoning_end"},
    {"key": "mp",      "label": "МП",         "short": "МП",  "start_field": "mp_start",            "end_field": "mp_end"},
    {"key": "tp",      "label": "ТП",         "short": "ТП",  "start_field": "tp_start",            "end_field": "tp_end"},
    {"key": "viz",     "label": "Визуал",     "short": "Виз", "start_field": "visualization_start", "end_field": "visualization_end"},
    {"key": "audit",   "label": "Аудит",      "short": "Ауд", "start_field": "audit_start",         "end_field": "audit_end"},
    {"key": "pjf",     "label": "PJF согл.",  "short": "PJF", "start_field": "pjf_approval_start",  "end_field": "pjf_approval_end"},
    {"key": "ds",      "label": "ДС",         "short": "ДС",  "start_field": None,                  "end_field": "ds_signing_date"},
    {"key": "tz",      "label": "ТЗ/Тендеры","short": "ТЗ",  "start_field": "tz_start",            "end_field": "tz_end"},
    {"key": "closure", "label": "Закрытие",   "short": "Закр","start_field": None,                  "end_field": "closure_date"},
    {"key": "vpk",     "label": "ВПК1",       "short": "ВПК", "start_field": None,                  "end_field": "vpk_date"},
    {"key": "opening", "label": "Открытие",   "short": "Откр","start_field": None,                  "end_field": "opening_date"},
]

TABS = [
    {"key": "all",                             "label": "Все"},
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


def _risk_score(row: dict) -> int:
    """Чем выше — тем критичнее проект."""
    return row["overdue_count"] * 100 + row["warn_count"] * 10


@router.get("/reconstruction", response_class=HTMLResponse)
async def reconstruction_page(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_executive),
    tab: str = "all",
    manager_id: str = None,
    only_problems: str = None,
    sort: str = "risk",
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

    projects_data = []
    overdue_items = []

    for p in projects:
        stages_info = []
        has_problem = False
        proj_done = 0
        proj_with_date = 0
        proj_overdue = 0
        proj_warn = 0

        for s in RECON_STAGES:
            end_val   = getattr(p, s["end_field"], None)
            start_val = getattr(p, s["start_field"], None) if s.get("start_field") else None
            status_rec = done_map.get((p.id, s["key"]))
            is_done = status_rec.is_done if status_rec else False
            done_by = status_rec.done_by if (status_rec and status_rec.is_done) else ""
            done_at = status_rec.done_at if (status_rec and status_rec.is_done) else None
            css = _cell_css(end_val, is_done, today)

            if css == "cell-over":
                has_problem = True
                proj_overdue += 1
                overdue_items.append({
                    "tk": p.tk_number,
                    "city": p.city or "",
                    "project_id": p.id,
                    "stage_label": s["label"],
                    "stage_key": s["key"],
                    "days": (today - end_val).days,
                    "manager": p.manager.name if p.manager else "—",
                    "manager_id": p.manager_id,
                    "end_date": end_val,
                })
            if css == "cell-warn":
                has_problem = True
                proj_warn += 1
            if css == "cell-done":
                proj_done += 1
            if end_val:
                proj_with_date += 1

            stages_info.append({
                "key": s["key"],
                "label": s["label"],
                "short": s["short"],
                "start_date": start_val,
                "end_date": end_val,
                "is_done": is_done,
                "done_by": done_by,
                "done_at": done_at,
                "css": css,
            })

        if only_problems and not has_problem:
            continue

        progress_pct = round(proj_done / proj_with_date * 100) if proj_with_date else 0
        is_opened = bool(p.opening_date and p.opening_date <= today)
        projects_data.append({
            "project": p,
            "stages": stages_info,
            "has_problem": has_problem,
            "stages_done": proj_done,
            "stages_total": proj_with_date,
            "overdue_count": proj_overdue,
            "warn_count": proj_warn,
            "progress_pct": progress_pct,
            "mgr_name": (p.manager.name if p.manager else ""),
            "is_opened": is_opened,
        })

    overdue_items.sort(key=lambda x: -x["days"])

    # Сортировка: открытые сверху → активные по риску → по дате открытия
    projects_data.sort(key=lambda r: (
        0 if r["is_opened"] else 1,                          # открытые первыми
        r["project"].opening_date if r["is_opened"]          # открытые: по дате открытия
            else date(2099, 1, 1),
        -_risk_score(r),                                     # активные: самые рисковые первыми
        r["project"].opening_date or date(2099, 1, 1),       # затем по плановой дате
    ))

    # Агрегаты для KPI-карточек
    overdue_projects = sum(1 for r in projects_data if r["overdue_count"] > 0)
    total_warn = sum(r["warn_count"] for r in projects_data)
    total_done_stages = sum(r["stages_done"] for r in projects_data)
    total_stages_with_date = sum(r["stages_total"] for r in projects_data)

    managers = db.query(models.Manager).filter(
        models.Manager.is_leader == False
    ).order_by(models.Manager.name).all()

    return templates.TemplateResponse("reconstruction.html", {
        "request": request,
        "user": user,
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
        # KPI
        "overdue_projects": overdue_projects,
        "total_warn": total_warn,
        "total_done_stages": total_done_stages,
        "total_stages_with_date": total_stages_with_date,
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

    p = db.query(models.Project).filter(models.Project.id == payload.project_id).first()
    end_val = None
    for s in RECON_STAGES:
        if s["key"] == payload.stage_key:
            end_val = getattr(p, s["end_field"], None)
            break
    css = _cell_css(end_val, payload.is_done, today)
    done_by = user.get("display_name", "") if payload.is_done else ""
    done_at_str = datetime.utcnow().strftime("%d.%m.%Y %H:%M") if payload.is_done else ""

    return JSONResponse({
        "ok": True,
        "css": css,
        "is_done": payload.is_done,
        "done_by": done_by,
        "done_at": done_at_str,
    })
