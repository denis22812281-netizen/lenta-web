from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address

from utils.csrf import get_csrf_token
from services.cloud_storage import media_url

templates = Jinja2Templates(directory="templates")
templates.env.globals["csrf_token"] = get_csrf_token
templates.env.globals["media_url"]  = media_url

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


def write_audit(request: Request, path: str | None = None):
    """Записывает посещение в audit_log. Вызывается из роутов вручную."""
    try:
        import database, models
        user = request.session.get("user")
        if not user:
            return
        p = path or request.url.path
        skip = ("/static", "/api/ping", "/api/online", "/favicon", "/admin/audit")
        if any(p.startswith(s) for s in skip):
            return
        db = database.SessionLocal()
        try:
            db.add(models.AuditLog(
                user_name=user.get("display_name", ""),
                user_phone=user.get("phone", ""),
                path=p,
                method=request.method,
                ip=request.client.host if request.client else "",
            ))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    except Exception:
        pass
