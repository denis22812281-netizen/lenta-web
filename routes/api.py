"""Общие API-эндпоинты: ping, online, task-notifications, deadlines, notifications, data-version."""
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Request, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import get_current_user
from services.online import ONLINE_USERS, ONLINE_TIMEOUT

router = APIRouter()


@router.post("/api/ping")
async def ping(request: Request):
    user = get_current_user(request)
    if user:
        now = datetime.utcnow()
        ONLINE_USERS[user.get("display_name", "")] = now
        stale = [k for k, ts in ONLINE_USERS.items()
                 if (now - ts).total_seconds() > ONLINE_TIMEOUT * 3]
        for k in stale:
            del ONLINE_USERS[k]
    return {"ok": True}


@router.get("/api/online")
async def get_online(request: Request):
    if not get_current_user(request):
        return {"online": []}
    now = datetime.utcnow()
    return {"online": [
        name for name, ts in ONLINE_USERS.items()
        if (now - ts).total_seconds() < ONLINE_TIMEOUT
    ]}


@router.get("/api/task-notifications")
async def get_task_notifications(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"notifications": [], "unread": 0}
    my_name = user.get("display_name", "")
    notifs = db.query(models.TaskNotification).filter(
        models.TaskNotification.recipient_name == my_name,
        models.TaskNotification.is_read == False,
    ).order_by(models.TaskNotification.created_at.desc()).limit(10).all()
    for n in notifs:
        n.is_read = True
    db.commit()
    return {
        "notifications": [{"id": n.id, "message": n.message, "task_id": n.task_id} for n in notifs],
        "unread": len(notifs),
    }


@router.get("/api/data-version")
async def data_version(db: Session = Depends(get_db)):
    result = db.query(func.max(models.Project.updated_at)).scalar()
    return {"version": result.isoformat() if result else "0"}


@router.get("/api/deadlines/check")
async def check_deadlines(request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return {"urgent_tasks": [], "overdue_tasks": [], "urgent_projects": []}
    today = date.today()
    urgent_tasks = db.query(models.Task).filter(
        models.Task.status != "Завершена", models.Task.deadline != None,
        models.Task.deadline >= today,
        models.Task.deadline <= today + timedelta(days=3)).all()
    overdue_tasks = db.query(models.Task).filter(
        models.Task.status != "Завершена", models.Task.deadline != None,
        models.Task.deadline < today).all()
    urgent_projects = db.query(models.Project).filter(
        models.Project.status != "Завершён", models.Project.end_date != None,
        models.Project.project_type == "Констракшн",
        models.Project.end_date >= today,
        models.Project.end_date <= today + timedelta(days=7),
        (models.Project.opening_date == None) | (models.Project.opening_date > today)
    ).all()
    return {
        "urgent_tasks": [{"id": t.id, "title": t.title, "deadline": str(t.deadline),
                          "assignee": t.assignee.name if t.assignee else "",
                          "days_left": (t.deadline - today).days} for t in urgent_tasks],
        "overdue_tasks": [{"id": t.id, "title": t.title, "deadline": str(t.deadline),
                           "assignee": t.assignee.name if t.assignee else "",
                           "days_overdue": (today - t.deadline).days} for t in overdue_tasks],
        "urgent_projects": [{"id": p.id, "name": p.name, "deadline": str(p.end_date),
                              "manager": p.manager.name if p.manager else "",
                              "days_left": (p.end_date - today).days} for p in urgent_projects],
    }


@router.get("/api/notifications/construction")
async def construction_notifications(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"notifications": []}
    today = date.today()
    display_name = user.get("display_name", "")
    managers = db.query(models.Manager).all()
    manager = None
    if display_name:
        name_part = display_name.split()[0].lower()
        for m in managers:
            if m.name.lower().startswith(name_part) or name_part in m.name.lower():
                manager = m; break
    is_leader = user.get("is_admin") or (manager and manager.is_leader)
    q = db.query(models.Project).filter(models.Project.project_type == "Констракшн")
    if not is_leader and manager:
        q = q.filter(models.Project.manager_id == manager.id)
    elif not is_leader:
        return {"notifications": []}
    notifications = []
    for p in q.all():
        tk = p.tk_number or str(p.id)
        mgr_name = p.manager.name if p.manager else ""
        if p.closure_date:
            days = (p.closure_date - today).days
            if 0 <= days <= 2:
                day_label = "сегодня" if days == 0 else ("завтра" if days == 1 else f"через {days} дня")
                notifications.append({"type": "smr", "urgency": "high",
                    "title": f"{mgr_name}: На ТК {tk} {day_label} выход на СМР",
                    "body": f"Дата СМР: {p.closure_date.strftime('%d.%m.%Y')}",
                    "date": str(p.closure_date)})
        if p.vpk_date:
            days = (p.vpk_date - today).days
            if 0 <= days <= 3:
                notifications.append({"type": "vpk", "urgency": "high",
                    "title": f"{mgr_name}: Через {days} дн на ТК {tk} ВПК1",
                    "body": f"Дата ВПК1: {p.vpk_date.strftime('%d.%m.%Y')}",
                    "date": str(p.vpk_date)})
        if p.opening_date and p.opening_date == today:
            notifications.append({"type": "opening", "urgency": "celebration",
                "title": "Поздравляю с открытием! 🎉",
                "body": f"{mgr_name}, поздравляю с открытием ТК {tk}!!!",
                "date": str(p.opening_date)})
    return {"notifications": notifications, "manager": manager.name if manager else "Все"}


@router.get("/api/notifications/reconstruct")
async def reconstruct_notifications(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"notifications": []}
    today = date.today()
    display_name = user.get("display_name", "")
    managers = db.query(models.Manager).all()
    manager = None
    if display_name:
        name_part = display_name.split()[0].lower()
        for m in managers:
            if m.name.lower().startswith(name_part) or name_part in m.name.lower():
                manager = m; break
    is_leader = user.get("is_admin") or (manager and manager.is_leader)
    q = db.query(models.Project).filter(models.Project.project_type == "Реконструкция")
    if not is_leader and manager:
        q = q.filter(models.Project.manager_id == manager.id)
    elif not is_leader:
        return {"notifications": []}
    notifications = []
    for p in q.all():
        tk = p.tk_number or str(p.id)
        mgr_name = p.manager.name if p.manager else ""
        if p.sid_start:
            days = (p.sid_start - today).days
            if 1 <= days <= 3:
                notifications.append({"type": "sid", "urgency": "high",
                    "title": f"{mgr_name}: ТК {tk} — приближается дата сбора данных",
                    "body": f"Начало СИД: {p.sid_start.strftime('%d.%m.%Y')} (через {days} дн)",
                    "date": str(p.sid_start)})
        if p.zoning_start:
            days = (p.zoning_start - today).days
            if days == 1:
                notifications.append({"type": "zoning", "urgency": "high",
                    "title": f"{mgr_name}: ТК {tk}, провести Зонирование",
                    "body": f"Начало зонирования завтра: {p.zoning_start.strftime('%d.%m.%Y')}",
                    "date": str(p.zoning_start)})
    return {"notifications": notifications, "manager": manager.name if manager else "Все"}
