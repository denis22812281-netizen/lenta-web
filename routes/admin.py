from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user
from utils.phone import normalize_phone

router = APIRouter()


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
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)
