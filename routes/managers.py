from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

import models
from config import MANAGER_LEADER_ORDER, MANAGER_NONLEADER_ORDER
from database import get_db
from deps import require_admin, require_login, templates
from services.cloud_storage import upload_photo
from services.online import ONLINE_TIMEOUT, ONLINE_USERS
from utils.phone import normalize_phone

router = APIRouter()

_UPLOAD_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _manager_sort_key(m: models.Manager) -> tuple[int, int]:
    order = MANAGER_LEADER_ORDER if m.is_leader else MANAGER_NONLEADER_ORDER
    pos   = order.index(m.name) if m.name in order else len(order)
    return (0 if m.is_leader else 1, pos)


@router.get("/managers", response_class=HTMLResponse)
async def managers_view(request: Request, db: Session = Depends(get_db),
                        user: dict = Depends(require_login)):
    today    = date.today()
    managers = db.query(models.Manager).options(
        joinedload(models.Manager.projects),
        joinedload(models.Manager.tasks),
    ).all()
    managers.sort(key=_manager_sort_key)

    stats        = []
    leader_stats = []
    for m in managers:
        recon    = [p for p in m.projects if p.project_type == "Реконструкция"]
        constr   = [p for p in m.projects if p.project_type == "Констракшн"]
        active   = sum(1 for p in m.projects if p.status == "Активный")
        open_t   = sum(1 for t in m.tasks if t.status != "Завершена")
        overdue  = sum(1 for t in m.tasks
                       if t.status != "Завершена" and t.deadline and t.deadline < today)
        urgent_p = [p for p in m.projects
                    if p.status == "Активный" and p.end_date
                    and 0 <= (p.end_date - today).days <= 14]
        stat = {
            "manager":         m,
            "active_projects": active,
            "open_tasks":      open_t,
            "overdue_tasks":   overdue,
            "urgent_projects": urgent_p,
            "recon_projects":  recon,
            "constr_projects": constr,
        }
        (leader_stats if m.is_leader else stats).append(stat)

    leader_stats.sort(
        key=lambda s: MANAGER_LEADER_ORDER.index(s["manager"].name)
        if s["manager"].name in MANAGER_LEADER_ORDER else 99
    )

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
                      email: str = Form(""), is_leader: str = Form(""),
                      user: dict = Depends(require_admin)):
    mgr = models.Manager(
        name=name.strip(),
        is_leader=bool(is_leader),
        email=email.strip().lower() if email.strip() else "",
    )
    db.add(mgr)
    db.flush()
    if phone.strip():
        normalized = normalize_phone(phone.strip())
        if not db.query(models.PhoneWhitelist).filter_by(phone=normalized).first():
            db.add(models.PhoneWhitelist(
                phone=normalized, display_name=name.strip(), is_admin=False,
            ))
    db.commit()
    return RedirectResponse("/managers", status_code=303)


@router.post("/managers/{manager_id}/delete")
async def delete_manager(manager_id: int, request: Request,
                         db: Session = Depends(get_db),
                         user: dict = Depends(require_admin)):
    mgr = db.query(models.Manager).filter_by(id=manager_id).first()
    if mgr:
        for p in mgr.projects:
            p.manager_id = None
        for t in mgr.tasks:
            t.assignee_id = None
        db.delete(mgr)
        db.commit()
    return RedirectResponse("/managers", status_code=303)


@router.post("/managers/{manager_id}/email")
async def update_manager_email(manager_id: int, request: Request,
                                db: Session = Depends(get_db),
                                user: dict = Depends(require_admin)):
    data  = await request.json()
    mgr   = db.query(models.Manager).filter_by(id=manager_id).first()
    if not mgr:
        raise HTTPException(status_code=404, detail="Менеджер не найден")
    email = data.get("email", "").strip().lower()
    if email:
        parts = email.split("@")
        if len(parts) != 2 or not parts[0] or "." not in parts[1]:
            raise HTTPException(status_code=422, detail="Некорректный email")
    mgr.email = email
    db.commit()
    return {"ok": True, "email": mgr.email}


@router.post("/managers/{manager_id}/photo")
async def upload_manager_photo(manager_id: int, request: Request,
                                file: UploadFile = File(...),
                                db: Session = Depends(get_db),
                                user: dict = Depends(require_admin)):
    mgr = db.query(models.Manager).filter_by(id=manager_id).first()
    if not mgr:
        raise HTTPException(status_code=404)
    ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    if ext not in _UPLOAD_PHOTO_EXTS:
        ext = ".jpg"
    content  = await file.read()
    mgr.photo = upload_photo(content, "managers", f"manager_{manager_id}{ext}")
    db.commit()
    return RedirectResponse("/managers", status_code=303)
