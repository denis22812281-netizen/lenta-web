"""Страница интерактивной аналитики — графики по всем модулям."""
import json
import time as _time
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import require_login, templates

router = APIRouter()

_CACHE_TTL = 300  # секунд (5 минут)
_cache_payload: dict | None = None
_cache_ts: float = 0


def _month_range(d: date):
    """Возвращает (start, end) для месяца даты d."""
    start = d.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _last_n_months(n: int, today: date) -> list[date]:
    """Список первых чисел последних n месяцев включая текущий."""
    months = []
    for i in range(n - 1, -1, -1):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        months.append(date(year, month, 1))
    return months


def _opening_color(p, today: date) -> str:
    if not p.opening_date or p.opening_date > today:
        return "active"
    if not p.end_date:
        return "ontime"
    if p.opening_date < p.end_date:
        return "early"
    if p.opening_date == p.end_date:
        return "ontime"
    return "late"


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    global _cache_payload, _cache_ts
    if _cache_payload and (_time.time() - _cache_ts) < _CACHE_TTL:
        return templates.TemplateResponse("analytics.html", {
            "request": request, "user": user, **_cache_payload,
        })

    today = date.today()
    months_12 = _last_n_months(12, today)
    month_labels = [m.strftime("%b %Y") for m in months_12]

    # ── 1. Открытия ТК по месяцам (Констракшн) ──────────────────────────────
    month_counts = []
    for m in months_12:
        start, end = _month_range(m)
        cnt = db.query(models.Project).filter(
            models.Project.project_type == "Констракшн",
            models.Project.opening_date >= start,
            models.Project.opening_date < end,
        ).count()
        month_counts.append(cnt)

    # ── 2. Итоги открытий (раньше / вовремя / позже) ────────────────────────
    completed = db.query(models.Project).filter(
        models.Project.project_type == "Констракшн",
        models.Project.opening_date.isnot(None),
    ).all()
    early_cnt  = sum(1 for p in completed if p.end_date and p.opening_date < p.end_date)
    ontime_cnt = sum(1 for p in completed if not p.end_date or p.opening_date == p.end_date)
    late_cnt   = sum(1 for p in completed if p.end_date and p.opening_date > p.end_date)

    # ── 3. Производительность менеджеров ────────────────────────────────────
    mgr_perf: dict[str, dict] = {}
    for p in completed:
        name = p.manager.name.split()[0] if p.manager else "Без менеджера"
        if name not in mgr_perf:
            mgr_perf[name] = {"early": 0, "ontime": 0, "late": 0}
        c = _opening_color(p, today)
        if c in mgr_perf[name]:
            mgr_perf[name][c] += 1
    mgr_names  = list(mgr_perf.keys())
    mgr_early  = [mgr_perf[n]["early"]  for n in mgr_names]
    mgr_ontime = [mgr_perf[n]["ontime"] for n in mgr_names]
    mgr_late   = [mgr_perf[n]["late"]   for n in mgr_names]

    # ── 4. Карточки адаптации по месяцам (последние 6) ──────────────────────
    adapt_months_6 = _last_n_months(6, today)
    adapt_labels_6 = [m.strftime("%b %Y") for m in adapt_months_6]
    adapt_bucket: dict[str, dict] = defaultdict(lambda: {"draft": 0, "sent": 0})
    for a in db.query(models.AdaptationCard).all():
        if a.created_at:
            key = a.created_at.strftime("%b %Y")
            adapt_bucket[key]["draft" if a.status == "draft" else "sent"] += 1
    adapt_draft = [adapt_bucket[m]["draft"] for m in adapt_labels_6]
    adapt_sent  = [adapt_bucket[m]["sent"]  for m in adapt_labels_6]

    # ── 5. Проекты по типам ──────────────────────────────────────────────────
    type_rows = db.query(
        models.Project.project_type,
        func.count(models.Project.id).label("cnt"),
    ).filter(models.Project.project_type != "").group_by(models.Project.project_type).all()
    type_labels = [r.project_type for r in type_rows]
    type_values = [r.cnt for r in type_rows]

    # ── 6. Задачи по статусам (donut) ───────────────────────────────────────
    task_rows = db.query(
        models.Task.status,
        func.count(models.Task.id).label("cnt"),
    ).group_by(models.Task.status).all()
    task_labels = [r.status for r in task_rows]
    task_values = [r.cnt for r in task_rows]

    # ── 7. Ближайшие дедлайны (горизонтальный бар) ──────────────────────────
    upcoming = db.query(models.Project).filter(
        models.Project.end_date >= today,
        models.Project.end_date <= today + timedelta(days=45),
        models.Project.status == "Активный",
        models.Project.project_type == "Констракшн",
        models.Project.opening_date.is_(None),
    ).order_by(models.Project.end_date).limit(10).all()
    dl_labels = [f"ТК {p.tk_number}" for p in upcoming]
    dl_days   = [(p.end_date - today).days for p in upcoming]
    dl_mgrs   = [p.manager.name.split()[0] if p.manager else "—" for p in upcoming]

    # ── Summary KPIs ─────────────────────────────────────────────────────────
    total_projects  = db.query(models.Project).count()
    active_projects = db.query(models.Project).filter(
        models.Project.status == "Активный").count()
    total_adapt = db.query(models.AdaptationCard).count()
    sent_adapt  = db.query(models.AdaptationCard).filter(
        models.AdaptationCard.status == "sent").count()

    _cache_payload = {
        # KPIs
        "total_projects": total_projects,
        "active_projects": active_projects,
        "total_adapt": total_adapt,
        "sent_adapt": sent_adapt,
        "total_construction": len(completed),
        "early_cnt": early_cnt,
        "ontime_cnt": ontime_cnt,
        "late_cnt": late_cnt,
        # Chart data (JSON)
        "j_month_labels": json.dumps(month_labels),
        "j_month_counts": json.dumps(month_counts),
        "j_result_labels": json.dumps(["Раньше срока", "Вовремя", "Позже срока"]),
        "j_result_values": json.dumps([early_cnt, ontime_cnt, late_cnt]),
        "j_mgr_names":  json.dumps(mgr_names),
        "j_mgr_early":  json.dumps(mgr_early),
        "j_mgr_ontime": json.dumps(mgr_ontime),
        "j_mgr_late":   json.dumps(mgr_late),
        "j_adapt_labels": json.dumps(adapt_labels_6),
        "j_adapt_draft":  json.dumps(adapt_draft),
        "j_adapt_sent":   json.dumps(adapt_sent),
        "j_type_labels": json.dumps(type_labels),
        "j_type_values": json.dumps(type_values),
        "j_task_labels": json.dumps(task_labels),
        "j_task_values": json.dumps(task_values),
        "j_dl_labels": json.dumps(dl_labels),
        "j_dl_days":   json.dumps(dl_days),
        "j_dl_mgrs":   json.dumps(dl_mgrs),
        "dl_count":    len(dl_labels),
    }
    _cache_ts = _time.time()
    return templates.TemplateResponse("analytics.html", {
        "request": request, "user": user, **_cache_payload,
    })
