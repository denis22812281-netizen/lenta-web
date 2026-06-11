from datetime import date, timedelta

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from deps import templates, require_executive

router = APIRouter()


@router.get("/leader", response_class=HTMLResponse)
async def leader_dashboard(request: Request, db: Session = Depends(get_db),
                           user: dict = Depends(require_executive)):
    today = date.today()
    tomorrow = today + timedelta(days=1)
    week_ahead = today + timedelta(days=7)
    month_ahead = today + timedelta(days=30)

    user_name = user.get("display_name", "")

    # Фото текущего пользователя из модели Manager
    current_manager = db.query(models.Manager).filter(
        models.Manager.name.ilike(f"%{user_name.split()[0]}%")
    ).first() if user_name else None
    current_manager_photo = current_manager.photo if current_manager and current_manager.photo else ""

    # ── ВПК непрочитанные ────────────────────────────────────────────────────
    total_vpk = db.query(models.VpkReport).count()
    read_by_me = db.query(models.VpkReportRead).filter(
        models.VpkReportRead.reader_name == user_name).count()
    vpk_unread = max(0, total_vpk - read_by_me)
    vpk_latest = db.query(models.VpkReport).options(
        joinedload(models.VpkReport.project)
    ).order_by(models.VpkReport.submitted_at.desc()).limit(5).all()

    # ── СМР дедлайны ─────────────────────────────────────────────────────────
    smr_today = db.query(models.SmrTask).options(
        joinedload(models.SmrTask.schedule).joinedload(models.SmrSchedule.project)
    ).filter(
        models.SmrTask.end_plan == today,
        models.SmrTask.status != "Выполнено"
    ).all()

    smr_tomorrow = db.query(models.SmrTask).options(
        joinedload(models.SmrTask.schedule).joinedload(models.SmrSchedule.project)
    ).filter(
        models.SmrTask.end_plan == tomorrow,
        models.SmrTask.status != "Выполнено"
    ).all()

    smr_week_count = db.query(models.SmrTask).filter(
        models.SmrTask.end_plan > tomorrow,
        models.SmrTask.end_plan <= week_ahead,
        models.SmrTask.status != "Выполнено"
    ).count()

    # ── Менеджеры с просроченными задачами ───────────────────────────────────
    overdue_by_manager = db.query(
        models.Manager.id,
        models.Manager.name,
        models.Manager.photo,
        func.count(models.Task.id).label("overdue_count")
    ).join(models.Task, models.Task.assignee_id == models.Manager.id).filter(
        models.Task.deadline < today,
        models.Task.status != "Завершена"
    ).group_by(
        models.Manager.id, models.Manager.name, models.Manager.photo
    ).order_by(func.count(models.Task.id).desc()).all()

    # ── Критичные проекты (открытие в ближайшие 30 дней) ─────────────────────
    critical_projects = db.query(models.Project).options(
        joinedload(models.Project.manager)
    ).filter(
        models.Project.opening_date >= today,
        models.Project.opening_date <= month_ahead,
        models.Project.status == "Активный",
        models.Project.project_type == "Констракшн"
    ).order_by(models.Project.opening_date).limit(5).all()

    # ── Задачи созданные мной ─────────────────────────────────────────────────
    my_tasks_open = db.query(models.Task).filter(
        models.Task.created_by == user_name,
        models.Task.status != "Завершена"
    ).count()
    my_tasks_overdue = db.query(models.Task).filter(
        models.Task.created_by == user_name,
        models.Task.status != "Завершена",
        models.Task.deadline < today
    ).count()
    my_recent_tasks = db.query(models.Task).options(
        joinedload(models.Task.assignee),
        joinedload(models.Task.project)
    ).filter(
        models.Task.created_by == user_name
    ).order_by(models.Task.created_at.desc()).limit(8).all()

    # ── Сводные счётчики ──────────────────────────────────────────────────────
    total_overdue_tasks = db.query(models.Task).filter(
        models.Task.deadline < today,
        models.Task.status != "Завершена"
    ).count()

    active_projects = db.query(models.Project).filter(
        models.Project.status == "Активный"
    ).count()

    week_end = today + timedelta(days=(6 - today.weekday()))
    opens_this_week = db.query(models.Project).filter(
        models.Project.end_date >= today,
        models.Project.end_date <= week_end,
        models.Project.status == "Активный",
        models.Project.project_type == "Констракшн"
    ).count()

    # ── Реконструкции: ТОП-3 критичных ──────────────────────────────────────
    recon_projects = db.query(models.Project).filter(
        models.Project.project_type == "Реконструкция",
        models.Project.status != "Приостановлен",
    ).options(joinedload(models.Project.manager)).all()

    recon_statuses = db.query(models.ReconStageStatus).all()
    done_set = {(s.project_id, s.stage_key) for s in recon_statuses if s.is_done}

    RECON_END_FIELDS = [
        ("sid","sid_end"),("zoning","zoning_end"),("mp","mp_end"),("tp","tp_end"),
        ("viz","visualization_end"),("audit","audit_end"),("pjf","pjf_approval_end"),
        ("ds","ds_signing_date"),("tz","tz_end"),("closure","closure_date"),
        ("vpk","vpk_date"),("opening","opening_date"),
    ]
    recon_data = []
    for p in recon_projects:
        overdue = warn = 0
        for key, field in RECON_END_FIELDS:
            end = getattr(p, field, None)
            if not end or (p.id, key) in done_set:
                continue
            days = (end - today).days
            if days < 0:
                overdue += 1
            elif days <= 7:
                warn += 1
        recon_data.append({"project": p, "overdue": overdue, "warn": warn})

    recon_data.sort(key=lambda r: -(r["overdue"] * 100 + r["warn"] * 10))
    recon_overdue_projects = sum(1 for r in recon_data if r["overdue"] > 0)
    recon_opened_list = sorted(
        [p for p in recon_projects if p.opening_date and p.opening_date <= today],
        key=lambda p: p.opening_date, reverse=True
    )
    recon_in_work_list = sorted(
        [p for p in recon_projects if not (p.opening_date and p.opening_date <= today)],
        key=lambda p: p.opening_date or date(2099,1,1)
    )
    recon_opened  = len(recon_opened_list)
    recon_in_work = len(recon_in_work_list)
    recon_top = recon_data[:4]

    return templates.TemplateResponse("leader.html", {
        "request": request, "user": user,
        "today": today,
        "vpk_unread": vpk_unread,
        "vpk_latest": vpk_latest,
        "smr_today": smr_today,
        "smr_tomorrow": smr_tomorrow,
        "smr_week_count": smr_week_count,
        "overdue_by_manager": overdue_by_manager,
        "critical_projects": critical_projects,
        "my_tasks_open": my_tasks_open,
        "my_tasks_overdue": my_tasks_overdue,
        "my_recent_tasks": my_recent_tasks,
        "total_overdue_tasks": total_overdue_tasks,
        "active_projects": active_projects,
        "opens_this_week": opens_this_week,
        "current_manager_photo": current_manager_photo,
        "recon_overdue_projects": recon_overdue_projects,
        "recon_total": len(recon_projects),
        "recon_opened": recon_opened,
        "recon_in_work": recon_in_work,
        "recon_opened_list": recon_opened_list,
        "recon_in_work_list": recon_in_work_list,
        "recon_top": recon_top,
    })
