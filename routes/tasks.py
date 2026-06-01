import os
from datetime import datetime, date
from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from deps import templates, get_current_user
from config import PRIORITIES, TASK_STATUSES
from services.email_service import notify_task_assigned, notify_task_status_changed, notify_task_completed

_TASK_REPORT_EMAILS = []
for _entry in os.getenv("TASK_REPORT_EMAILS", "").split(","):
    _entry = _entry.strip()
    if not _entry:
        continue
    if ":" in _entry:
        _e, _n = _entry.split(":", 1)
        _TASK_REPORT_EMAILS.append((_e.strip(), _n.strip()))
    else:
        _TASK_REPORT_EMAILS.append((_entry, _entry.split("@")[0]))

router = APIRouter()


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_view(request: Request, db: Session = Depends(get_db),
                     manager_id: str = None, status: str = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    my_name  = user.get("display_name", "")
    is_admin = user.get("is_admin", False)
    my_manager = db.query(models.Manager).filter(models.Manager.name == my_name).first()

    q = db.query(models.Task)
    if not is_admin:
        conditions = [models.Task.created_by == my_name]
        if my_manager:
            conditions.append(models.Task.assignee_id == my_manager.id)
        q = q.filter(or_(*conditions))
    else:
        if manager_id and str(manager_id).isdigit():
            q = q.filter(models.Task.assignee_id == int(manager_id))
    if status:
        q = q.filter(models.Task.status == status)

    tasks = q.options(
        joinedload(models.Task.assignee),
        joinedload(models.Task.project),
    ).order_by(models.Task.deadline.nullslast()).all()

    managers = db.query(models.Manager).all()
    projects = db.query(models.Project).filter(models.Project.status == "Активный").all()
    unread_notifs = db.query(models.TaskNotification).filter(
        models.TaskNotification.recipient_name == my_name,
        models.TaskNotification.is_read == False,
    ).count()

    return templates.TemplateResponse("create_task.html", {
        "request": request, "user": user,
        "tasks": tasks, "managers": managers, "projects": projects,
        "priorities": PRIORITIES, "task_statuses": TASK_STATUSES,
        "today": date.today(),
        "filter_manager_id": manager_id, "filter_status": status,
        "unread_notifs": unread_notifs,
    })


@router.post("/tasks/create")
async def create_task(request: Request, db: Session = Depends(get_db),
                      title: str = Form(...), description: str = Form(""),
                      project_id: str = Form(""), assignee_id: str = Form(""),
                      deadline: str = Form(""), priority: str = Form("Средний")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    creator = user.get("display_name", "")
    task = models.Task(
        title=title, description=description,
        project_id=int(project_id) if project_id else None,
        assignee_id=int(assignee_id) if assignee_id else None,
        deadline=datetime.strptime(deadline, "%Y-%m-%d").date() if deadline else None,
        priority=priority, created_by=creator,
    )
    db.add(task)
    db.flush()
    if assignee_id:
        assignee = db.query(models.Manager).filter(
            models.Manager.id == int(assignee_id)).first()
        if assignee and assignee.name != creator:
            dl = f", дедлайн {task.deadline.strftime('%d.%m.%Y')}" if task.deadline else ""
            db.add(models.TaskNotification(
                recipient_name=assignee.name, task_id=task.id,
                message=f"📋 {creator} поставил вам задачу: «{title}»{dl}",
            ))
            # Email-уведомление (если email настроен у менеджера)
            if assignee.email:
                proj = db.query(models.Project).filter(
                    models.Project.id == task.project_id).first() if task.project_id else None
                notify_task_assigned(
                    to_email=assignee.email,
                    assignee_name=assignee.name,
                    task_title=title,
                    creator=creator,
                    deadline_str=task.deadline.strftime("%d.%m.%Y") if task.deadline else "",
                    project_name=proj.name if proj else "",
                )
    db.commit()
    return RedirectResponse("/tasks", status_code=303)


@router.post("/tasks/{task_id}/update-status")
async def update_task_status(task_id: int, request: Request, db: Session = Depends(get_db),
                             status: str = Form(...), completion_comment: str = Form(""),
                             photos: list[UploadFile] = File(default=[])):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    t = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not t:
        return RedirectResponse("/tasks", status_code=303)

    old_status = t.status
    t.status = status
    comment = completion_comment.strip()
    if status == "Завершена" and comment:
        t.completion_comment = comment

    # Сохраняем фото (только при завершении)
    saved_photos = []
    if status == "Завершена" and photos:
        photo_dir = Path("static/uploads/tasks")
        photo_dir.mkdir(parents=True, exist_ok=True)
        _ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
        _MAX_SIZE = 20 * 1024 * 1024  # 20 MB
        for ph in photos:
            if not ph.filename:
                continue
            ext = Path(ph.filename).suffix.lower() or ".jpg"
            if ext not in _ALLOWED_EXT:
                continue
            raw = await ph.read()
            if len(raw) > _MAX_SIZE:
                continue
            fname = f"{task_id}_{int(datetime.utcnow().timestamp())}_{ph.filename[:20]}{ext}"
            fname = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)
            # Сжимаем через Pillow если доступен
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                img.thumbnail((1200, 1200), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70, optimize=True)
                raw = buf.getvalue()
                ext = ".jpg"
                fname = fname.rsplit(".", 1)[0] + ".jpg"
            except Exception:
                pass
            (photo_dir / fname).write_bytes(raw)
            rel = f"uploads/tasks/{fname}"
            db.add(models.TaskPhoto(task_id=task_id, photo_path=rel,
                                    uploaded_by=user.get("display_name", "")))
            saved_photos.append(rel)

    db.flush()

    if t.created_by and t.created_by != user.get("display_name", "") and old_status != status:
        icon = "✅" if status == "Завершена" else "🔄"
        msg = f"{icon} Задача «{t.title}»: статус изменён на «{status}»"
        if status == "Завершена" and comment:
            msg += f"\nКомментарий: {comment}"
        db.add(models.TaskNotification(recipient_name=t.created_by, task_id=t.id, message=msg))

    db.commit()

    # Email-отчёт при завершении
    if status == "Завершена" and old_status != "Завершена":
        assignee_name = t.assignee.name if t.assignee else user.get("display_name", "")
        # Все фото задачи (включая только что сохранённые)
        all_photos = [p.photo_path for p in db.query(models.TaskPhoto).filter(
            models.TaskPhoto.task_id == task_id).all()]

        recipients = {}
        # Создатель задачи
        creator_mgr = db.query(models.Manager).filter(
            models.Manager.name == t.created_by).first()
        if creator_mgr and creator_mgr.email:
            recipients[creator_mgr.email] = creator_mgr.name
        # Исполнитель задачи
        if t.assignee and t.assignee.email and t.assignee.email not in recipients:
            recipients[t.assignee.email] = t.assignee.name

        for email, name in recipients.items():
            notify_task_completed(
                to_email=email,
                creator_name=name,
                task_title=t.title,
                assignee_name=assignee_name,
                comment=comment,
                photo_paths=all_photos,
                project_name=t.project.name if t.project else "",
            )

    return RedirectResponse("/tasks", status_code=303)


@router.post("/tasks/{task_id}/delete")
async def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    t = db.query(models.Task).filter(models.Task.id == task_id).first()
    if t:
        db.delete(t)
        db.commit()
    return RedirectResponse("/tasks", status_code=303)


@router.get("/api/tasks")
async def api_tasks_json(request: Request, db: Session = Depends(get_db),
                         manager_id: str = None, status: str = None):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    my_name  = user.get("display_name", "")
    is_admin = user.get("is_admin", False)
    my_manager = db.query(models.Manager).filter(models.Manager.name == my_name).first()

    q = db.query(models.Task)
    if not is_admin:
        conditions = [models.Task.created_by == my_name]
        if my_manager:
            conditions.append(models.Task.assignee_id == my_manager.id)
        q = q.filter(or_(*conditions))
    else:
        if manager_id and str(manager_id).isdigit():
            q = q.filter(models.Task.assignee_id == int(manager_id))
    if status:
        q = q.filter(models.Task.status == status)

    today = date.today()
    tasks = q.options(
        joinedload(models.Task.assignee),
        joinedload(models.Task.project),
    ).order_by(models.Task.deadline.nullslast()).all()

    result = []
    for t in tasks:
        days = (t.deadline - today).days if t.deadline else None
        result.append({
            "id": t.id,
            "title": t.title,
            "description": t.description or "",
            "assignee": t.assignee.name if t.assignee else "",
            "assignee_id": t.assignee_id,
            "created_by": t.created_by or "",
            "project": t.project.name if t.project else "",
            "deadline": t.deadline.strftime("%d.%m.%Y") if t.deadline else "",
            "deadline_days": days,
            "priority": t.priority,
            "status": t.status,
            "completion_comment": t.completion_comment or "",
        })
    return JSONResponse({"tasks": result, "total": len(result)})
