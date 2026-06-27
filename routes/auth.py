import base64
import io
import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import get_current_user, limiter, require_login, templates
from utils.passwords import _is_legacy_hash, hash_password, verify_password
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
    # 2FA check
    if getattr(user, "totp_enabled", False) and user.totp_secret:
        request.session["pending_2fa"] = {
            "user_id": user.id,
            "phone": user.phone,
            "display_name": user.display_name or "",
        }
        return RedirectResponse("/login?step=2fa", status_code=302)
    request.session.clear()
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
    request.session.clear()
    _set_session(request, user, db)
    return RedirectResponse("/", status_code=302)


@router.post("/login/2fa")
@limiter.limit("10/minute")
async def login_2fa(request: Request, db: Session = Depends(get_db),
                    phone: str = Form(...), totp_code: str = Form(...)):
    pending = request.session.get("pending_2fa")
    if not pending or pending.get("phone") != phone:
        return RedirectResponse("/login", status_code=302)
    user = db.query(models.User).filter(models.User.phone == phone).first()
    if not user:
        return RedirectResponse("/login", status_code=302)
    try:
        import pyotp
        ok = pyotp.TOTP(user.totp_secret).verify(totp_code.strip(), valid_window=1)
    except Exception:
        ok = False
    if not ok:
        return templates.TemplateResponse("login.html", {
            "request": request, "step": "2fa",
            "phone": phone,
            "display_name": pending.get("display_name", ""),
            "error": "Неверный код. Откройте приложение и введите текущий код.",
        })
    request.session.clear()
    _set_session(request, user, db)
    return RedirectResponse("/", status_code=302)


@router.get("/account/2fa", response_class=HTMLResponse)
async def account_2fa_page(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    db_user = db.query(models.User).filter(models.User.id == user["id"]).first()
    try:
        import pyotp
        import qrcode as _qrcode
        secret = db_user.totp_secret or pyotp.random_base32()
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.get("display_name", "user"),
            issuer_name="Лента Проекты",
        )
        qr = _qrcode.QRCode(box_size=6, border=2)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        secret, qr_b64 = "", ""

    return templates.TemplateResponse("account_2fa.html", {
        "request": request,
        "user": user,
        "db_user": db_user,
        "secret": secret,
        "qr_b64": qr_b64,
        "totp_enabled": getattr(db_user, "totp_enabled", False),
    })


@router.post("/account/2fa/enable")
async def account_2fa_enable(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
    totp_code: str = Form(...),
    secret: str = Form(...),
):
    try:
        import pyotp
        ok = pyotp.TOTP(secret).verify(totp_code.strip(), valid_window=1)
    except Exception:
        ok = False
    if not ok:
        return RedirectResponse("/account/2fa?error=invalid_code", status_code=303)
    db_user = db.query(models.User).filter(models.User.id == user["id"]).first()
    db_user.totp_secret = secret
    db_user.totp_enabled = True
    db.commit()
    return RedirectResponse("/account/2fa?enabled=1", status_code=303)


@router.post("/account/2fa/disable")
async def account_2fa_disable(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    db_user = db.query(models.User).filter(models.User.id == user["id"]).first()
    db_user.totp_enabled = False
    db_user.totp_secret = None
    db.commit()
    return RedirectResponse("/account/2fa?disabled=1", status_code=303)


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
