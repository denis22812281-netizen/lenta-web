from datetime import datetime, date
from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user
from utils.phone import normalize_phone
from services.online import ONLINE_USERS, ONLINE_TIMEOUT

router = APIRouter()


@router.get("/managers", response_class=HTMLResponse)
async def managers_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    today = date.today()
    _order = [
        "Месмер Денис", "Митько Роберт", "Ловчиков Александр",
        "Валеев Борис", "Косило Сергей", "Студеникин Сергей",
        "Хачатурова Жанна", "Шевченко Наталья",
    ]
    managers = db.query(models.Manager).all()
    managers.sort(key=lambda m: (
        0 if m.is_leader else 1,
        _order.index(m.name) if m.name in _order else 99
    ))
    stats = []
    leader_stats = []
    for m in managers:
        recon  = [p for p in m.projects if p.project_type == "Реконструкция"]
        constr = [p for p in m.projects if p.project_type == "Констракшн"]
        active = sum(1 for p in m.projects if p.status == "Активный")
        open_t = sum(1 for t in m.tasks if t.status != "Завершена")
        overdue = sum(1 for t in m.tasks
                      if t.status != "Завершена" and t.deadline and t.deadline < today)
        urgent_p = [p for p in m.projects
                    if p.status == "Активный" and p.end_date
                    and 0 <= (p.end_date - today).days <= 14]
        stat = {"manager": m, "active_projects": active,
                "open_tasks": open_t, "overdue_tasks": overdue,
                "urgent_projects": urgent_p,
                "recon_projects": recon, "constr_projects": constr}
        if m.is_leader:
            leader_stats.append(stat)
        else:
            stats.append(stat)
    leader_stats.sort(key=lambda s: 0 if "Комаров" in s["manager"].name else 1)
    now = datetime.utcnow()
    online_set = {
        name for name, ts in ONLINE_USERS.items()
        if (now - ts).total_seconds() < ONLINE_TIMEOUT
    }
    return templates.TemplateResponse("managers.html", {
        "request": request, "user": user,
        "manager_stats": stats, "leader_stats": leader_stats,
        "today": today, "online_set": online_set,
    })


@router.post("/managers/add")
async def add_manager(request: Request, db: Session = Depends(get_db),
                      name: str = Form(...), phone: str = Form(""),
                      is_leader: str = Form("")):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse("/managers", status_code=302)
    mgr = models.Manager(name=name.strip(), is_leader=bool(is_leader))
    db.add(mgr)
    db.flush()
    if phone.strip():
        normalized = normalize_phone(phone.strip())
        if not db.query(models.PhoneWhitelist).filter(
                models.PhoneWhitelist.phone == normalized).first():
            db.add(models.PhoneWhitelist(
                phone=normalized, display_name=name.strip(), is_admin=False))
    db.commit()
    return RedirectResponse("/managers", status_code=303)


@router.post("/managers/{manager_id}/delete")
async def delete_manager(manager_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse("/managers", status_code=302)
    mgr = db.query(models.Manager).filter(models.Manager.id == manager_id).first()
    if mgr:
        for p in mgr.projects:
            p.manager_id = None
        for t in mgr.tasks:
            t.assignee_id = None
        db.delete(mgr)
        db.commit()
    return RedirectResponse("/managers", status_code=303)


@router.post("/managers/{manager_id}/photo")
async def upload_manager_photo(manager_id: int, request: Request,
                                file: UploadFile = File(...),
                                db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user or user.get("display_name") != "Месмер Денис":
        return RedirectResponse("/managers", status_code=302)
    mgr = db.query(models.Manager).filter(models.Manager.id == manager_id).first()
    if not mgr:
        raise HTTPException(status_code=404)
    ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        ext = '.jpg'
    save_dir = Path("static/img/managers")
    save_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{manager_id}{ext}"
    (save_dir / filename).write_bytes(await file.read())
    mgr.photo = f"img/managers/{filename}"
    db.commit()
    return RedirectResponse("/managers", status_code=303)
