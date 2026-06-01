import os
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user
from utils.phone import normalize_phone

router = APIRouter()

_AUDIT_ALLOWED_PHONE = os.getenv("ADMIN_PHONE", "+79997303914")


def _is_audit_allowed(user: dict) -> bool:
    return user and user.get("phone") == _AUDIT_ALLOWED_PHONE


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse("/", status_code=302)
    whitelist = db.query(models.PhoneWhitelist).order_by(
        models.PhoneWhitelist.created_at).all()
    users = db.query(models.User).all()
    user_by_phone = {u.phone: u for u in users}
    return templates.TemplateResponse("admin_users.html", {
        "request": request, "user": user,
        "whitelist": whitelist, "user_by_phone": user_by_phone,
    })


@router.post("/admin/whitelist/add")
async def add_to_whitelist(request: Request, db: Session = Depends(get_db),
                           phone: str = Form(...), display_name: str = Form(""),
                           is_admin: str = Form("")):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse("/", status_code=302)
    normalized = normalize_phone(phone)
    if not db.query(models.PhoneWhitelist).filter(
            models.PhoneWhitelist.phone == normalized).first():
        db.add(models.PhoneWhitelist(
            phone=normalized, display_name=display_name.strip(),
            is_admin=bool(is_admin),
        ))
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/whitelist/{wl_id}/delete")
async def remove_from_whitelist(wl_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse("/", status_code=302)
    wl = db.query(models.PhoneWhitelist).filter(models.PhoneWhitelist.id == wl_id).first()
    if wl:
        linked = db.query(models.User).filter(models.User.phone == wl.phone).first()
        if linked and linked.id != user.get("id"):
            db.delete(linked)
        db.delete(wl)
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/reset-password")
async def reset_password(user_id: int, request: Request, db: Session = Depends(get_db)):
    current = get_current_user(request)
    if not current or not current.get("is_admin"):
        return RedirectResponse("/", status_code=302)
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if u:
        u.password_hash = None
        u.session_version = (u.session_version or 1) + 1
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/admin/audit", response_class=HTMLResponse)
async def audit_log(request: Request, db: Session = Depends(get_db),
                    user_filter: str = "", limit: int = 200):
    user = get_current_user(request)
    if not user or not _is_audit_allowed(user):
        return RedirectResponse("/", status_code=302)
    q = db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc())
    if user_filter:
        q = q.filter(models.AuditLog.user_name == user_filter)
    logs = q.limit(limit).all()
    users = [r[0] for r in db.query(models.AuditLog.user_name).distinct().all() if r[0]]
    return templates.TemplateResponse("audit_log.html", {
        "request": request, "user": user,
        "logs": logs, "users": users,
        "user_filter": user_filter,
    })


@router.post("/admin/audit/clear")
async def audit_clear(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user or not _is_audit_allowed(user):
        return RedirectResponse("/", status_code=302)
    db.query(models.AuditLog).delete()
    db.commit()
    return RedirectResponse("/admin/audit", status_code=303)
