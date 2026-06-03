"""График СМР — создание, просмотр, управление задачами, email-подтверждения."""
import os, secrets
from datetime import date, timedelta, datetime

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user
from services.smr_template import SMR_TEMPLATE
from services.email_service import send_smr_confirmation

router = APIRouter()

APP_URL = os.getenv("APP_URL", "https://lenta-web-production.up.railway.app").rstrip("/")


# ── Создать график по шаблону ─────────────────────────────────────────────────

@router.post("/smr/create/{project_id}")
async def smr_create(project_id: int, request: Request,
                     start_date: str = Form(...),
                     db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    proj = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404)

    # Если уже есть — удалить старый
    existing = db.query(models.SmrSchedule).filter(
        models.SmrSchedule.project_id == project_id).first()
    if existing:
        db.delete(existing)
        db.flush()

    try:
        base = date.fromisoformat(start_date)
    except ValueError:
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    schedule = models.SmrSchedule(project_id=project_id)
    db.add(schedule)
    db.flush()

    for i, (name, s_day, e_day, is_ms) in enumerate(SMR_TEMPLATE):
        db.add(models.SmrTask(
            schedule_id=schedule.id,
            name=name,
            order=i,
            start_plan=base + timedelta(days=s_day),
            end_plan=base + timedelta(days=e_day),
            is_milestone=is_ms,
            status="Запланировано",
        ))
    db.commit()
    return RedirectResponse(f"/smr/{project_id}", status_code=303)


# ── Просмотр графика ─────────────────────────────────────────────────────────

@router.get("/smr/{project_id}", response_class=HTMLResponse)
async def smr_view(project_id: int, request: Request,
                   db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    proj = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404)

    schedule = db.query(models.SmrSchedule).filter(
        models.SmrSchedule.project_id == project_id).first()

    today = date.today()
    gantt_start = gantt_end = None
    if schedule and schedule.tasks:
        dates = [t.start_plan for t in schedule.tasks if t.start_plan] + \
                [t.end_plan   for t in schedule.tasks if t.end_plan]
        if dates:
            gantt_start = min(dates)
            gantt_end   = max(dates)

    return templates.TemplateResponse("smr_schedule.html", {
        "request": request, "user": user,
        "proj": proj, "schedule": schedule,
        "today": today,
        "gantt_start": gantt_start,
        "gantt_end":   gantt_end,
    })


# ── Обновить статус задачи (AJAX) ────────────────────────────────────────────

@router.post("/api/smr/task/{task_id}/status")
async def smr_task_status(task_id: int, request: Request,
                          db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    task = db.query(models.SmrTask).filter(models.SmrTask.id == task_id).first()
    if not task:
        return JSONResponse({"error": "Не найдено"}, status_code=404)
    task.status = data.get("status", task.status)
    db.commit()
    return {"ok": True, "status": task.status}


# ── Обновить email ответственных (AJAX) ──────────────────────────────────────

@router.post("/api/smr/task/{task_id}/emails")
async def smr_task_emails(task_id: int, request: Request,
                          db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    task = db.query(models.SmrTask).filter(models.SmrTask.id == task_id).first()
    if not task:
        return JSONResponse({"error": "Не найдено"}, status_code=404)
    task.notify_email1 = data.get("email1", "").strip().lower()
    task.notify_email2 = data.get("email2", "").strip().lower()
    db.commit()
    return {"ok": True}


# ── Отправить запрос на подтверждение ────────────────────────────────────────

@router.post("/api/smr/task/{task_id}/send-confirm")
async def smr_send_confirm(task_id: int, request: Request,
                           db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    task = db.query(models.SmrTask).filter(models.SmrTask.id == task_id).first()
    if not task:
        return JSONResponse({"error": "Не найдено"}, status_code=404)

    proj = task.schedule.project
    sent = []

    for email in [task.notify_email1, task.notify_email2]:
        if not email:
            continue
        token = secrets.token_hex(32)
        db.add(models.SmrConfirmation(task_id=task.id, token=token, email=email))
        confirm_url = f"{APP_URL}/smr/confirm/{token}"
        reject_url  = f"{APP_URL}/smr/confirm/{token}?action=reject"
        try:
            send_smr_confirmation(
                to_email=email,
                task_name=task.name,
                project_name=proj.name,
                tk_number=proj.tk_number,
                plan_date=task.end_plan.strftime("%d.%m.%Y") if task.end_plan else "—",
                confirm_url=confirm_url,
                reject_url=reject_url,
            )
            sent.append(email)
        except Exception as e:
            pass

    db.commit()
    return {"ok": True, "sent": sent}


# ── Публичная страница подтверждения (без авторизации) ───────────────────────

@router.get("/smr/confirm/{token}", response_class=HTMLResponse)
async def smr_confirm_page(token: str, request: Request,
                           action: str = "confirm",
                           db: Session = Depends(get_db)):
    conf = db.query(models.SmrConfirmation).filter(
        models.SmrConfirmation.token == token).first()

    if not conf:
        return templates.TemplateResponse("smr_confirm.html", {
            "request": request, "error": "Ссылка недействительна или устарела."
        })

    already_done = bool(conf.action)

    if not already_done:
        conf.action       = "confirmed" if action != "reject" else "rejected"
        conf.responded_at = datetime.utcnow()
        db.commit()

    task = conf.task
    proj = task.schedule.project if task and task.schedule else None

    return templates.TemplateResponse("smr_confirm.html", {
        "request": request,
        "conf": conf,
        "task": task,
        "proj": proj,
        "already_done": already_done,
    })


# ── Удалить график ────────────────────────────────────────────────────────────

@router.post("/smr/delete/{project_id}")
async def smr_delete(project_id: int, request: Request,
                     db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    sch = db.query(models.SmrSchedule).filter(
        models.SmrSchedule.project_id == project_id).first()
    if sch:
        db.delete(sch)
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=303)
