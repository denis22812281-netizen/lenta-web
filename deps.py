from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address

from services.cloud_storage import media_url
from utils.csrf import get_csrf_token

templates = Jinja2Templates(directory="templates")
templates.env.globals["csrf_token"] = get_csrf_token
templates.env.globals["media_url"]  = media_url

def _short_name(name: str) -> str:
    """'Ловчиков Александр' → 'Ловчиков А.'"""
    parts = (name or "").strip().split()
    return f"{parts[0]} {parts[1][0]}." if len(parts) >= 2 else name

templates.env.filters["short_name"] = _short_name

_AVATAR_COLORS = [
    "#1d4ed8","#7c3aed","#be185d","#b45309",
    "#065f46","#b91c1c","#0e7490","#4338ca",
    "#0369a1","#6d28d9","#9d174d","#92400e",
]

def _avatar_color(name: str) -> str:
    """Stable color for a name — used for manager initials avatars."""
    if not name:
        return _AVATAR_COLORS[0]
    return _AVATAR_COLORS[sum(ord(c) for c in name) % len(_AVATAR_COLORS)]

templates.env.filters["avatar_color"] = _avatar_color

# Rate limiter (shared между роутерами)
limiter = Limiter(key_func=get_remote_address)


def get_current_user(request: Request):
    return request.session.get("user")


def require_login(request: Request) -> dict:
    """FastAPI Dependency: возвращает пользователя или редиректит на /login."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


def require_admin(request: Request) -> dict:
    """FastAPI Dependency: требует is_admin, иначе редирект на /."""
    user = require_login(request)
    if not user.get("is_admin"):
        raise HTTPException(status_code=302, headers={"Location": "/"})
    return user


def require_executive(request: Request) -> dict:
    """FastAPI Dependency: is_admin ИЛИ is_leader-менеджер (Комаров, Гаврин)."""
    user = require_login(request)
    if user.get("is_admin"):
        return user
    try:
        import database
        import models
        name = user.get("display_name", "")
        if name:
            with database.db_session() as db:
                mgr = db.query(models.Manager).filter(
                    models.Manager.name.ilike(f"%{name.split()[0]}%"),
                    models.Manager.is_leader == True,
                ).first()
                if mgr:
                    return user
    except Exception:
        pass
    raise HTTPException(status_code=302, headers={"Location": "/"})


def require_api_user(request: Request) -> dict:
    """Dependency для API-эндпоинтов: возвращает 401 JSON вместо 302 redirect."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"ok": False, "error": "Unauthorized", "redirect": "/login"},
        )
    return user


def write_audit(request: Request, path: str | None = None):
    """Записывает посещение в audit_log. Вызывается из роутов вручную."""
    try:
        import database
        import models
        user = request.session.get("user")
        if not user:
            return
        p = path or request.url.path
        skip = ("/static", "/api/ping", "/api/online", "/favicon", "/admin/audit")
        if any(p.startswith(s) for s in skip):
            return
        with database.db_session() as db:
            db.add(models.AuditLog(
                user_name=user.get("display_name", ""),
                user_phone=user.get("phone", ""),
                path=p,
                method=request.method,
                ip=request.client.host if request.client else "",
            ))
    except Exception:
        pass
