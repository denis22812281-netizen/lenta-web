import os

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user, limiter
from utils.passwords import hash_password, verify_password, _is_legacy_hash
from utils.phone import normalize_phone

router = APIRouter()

_APP_URL = os.getenv("APP_URL", "https://lenta-web-production.up.railway.app").rstrip("/")


@router.get("/qr", response_class=HTMLResponse)
async def qr_page(request: Request):
    return templates.TemplateResponse("qr.html", {"request": request, "app_url": _APP_URL})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/", status_code=302)
    step = request.query_params.get("step", "")
    pending = request.session.get("pending_2fa")
    if step == "2fa" and pending:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "step": "2fa",
            "phone": pending["phone"],
            "display_name": pending["display_name"],
        })
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login/check-phone")
@limiter.limit("20/minute")
async def check_phone(request: Request, db: Session = Depends(get_db),
                      phone: str = Form(...)):
    normalized = normalize_phone(phone)
    wl = db.query(models.PhoneWhitelist).filter(
        models.PhoneWhitelist.phone == normalized).first()
    if not wl:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Доступ закрыт. Этот номер не авторизован.",
        })
    user = db.query(models.User).filter(models.User.phone == normalized).first()
    if user and user.password_hash:
        return templates.TemplateResponse("login.html", {
            "request": request, "step": "password",
            "phone": normalized,
            "display_name": user.display_name or wl.display_name,
        })
    return templates.TemplateResponse("login.html", {
        "request": request, "step": "create_password",
        "phone": normalized, "display_name": wl.display_name,
    })


@router.post("/login/enter")
@limiter.limit("5/minute")
async def login_enter(request: Request, db: Session = Depends(get_db),
                      phone: str = Form(...), password: str = Form(...),
                      remember: str = Form("")):
    normalized = normalize_phone(phone)
    user = db.query(models.User).filter(models.User.phone == normalized).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request, "step": "password",
            "phone": normalized,
            "display_name": user.display_name if user else "",
            "error": "Неверный пароль",
        })
    if _is_legacy_hash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    _set_session(request, user, db)
    return RedirectResponse("/", status_code=302)


@router.post("/login/create-password")
@limiter.limit("10/minute")
async def create_password(request: Request, db: Session = Depends(get_db),
                          phone: str = Form(...), password: str = Form(...),
                          password2: str = Form(...)):
    normalized = normalize_phone(phone)
    wl = db.query(models.PhoneWhitelist).filter(
        models.PhoneWhitelist.phone == normalized).first()
    if not wl:
        return RedirectResponse("/login", status_code=302)
    if len(password) < 8:
        return templates.TemplateResponse("login.html", {
            "request": request, "step": "create_password",
            "phone": normalized, "display_name": wl.display_name,
            "error": "Пароль должен быть не менее 8 символов",
        })
    if password != password2:
        return templates.TemplateResponse("login.html", {
            "request": request, "step": "create_password",
            "phone": normalized, "display_name": wl.display_name,
            "error": "Пароли не совпадают",
        })
    user = db.query(models.User).filter(models.User.phone == normalized).first()
    if user:
        user.password_hash = hash_password(password)
    else:
        user = models.User(
            phone=normalized, username=normalized,
            password_hash=hash_password(password),
            display_name=wl.display_name, is_admin=wl.is_admin,
        )
        db.add(user)
    db.commit()
    db.refresh(user)
    _set_session(request, user, db)
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


def _set_session(request: Request, user: models.User, db: Session | None = None):
    is_leader = False
    if db and not user.is_admin:
        try:
            first_name = (user.display_name or "").split()[0]
            if first_name:
                mgr = db.query(models.Manager).filter(
                    models.Manager.name.ilike(f"%{first_name}%"),
                    models.Manager.is_leader == True,
                ).first()
                is_leader = bool(mgr)
        except Exception:
            pass
    request.session["user"] = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "is_leader": is_leader,
        "phone": user.phone,
        "sv": user.session_version or 1,
    }
