import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import get_current_user, require_admin, require_login, templates
from utils.phone import normalize_phone

router = APIRouter()

_AUDIT_ALLOWED_PHONE = os.getenv("ADMIN_PHONE", "")


def _is_audit_allowed(user: dict) -> bool:
    return user and user.get("phone") == _AUDIT_ALLOWED_PHONE


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, db: Session = Depends(get_db),
                      user: dict = Depends(require_admin)):
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
                           user: dict = Depends(require_admin),
                           phone: str = Form(...), display_name: str = Form(""),
                           is_admin: str = Form("")):
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
async def remove_from_whitelist(wl_id: int, request: Request, db: Session = Depends(get_db),
                                 user: dict = Depends(require_admin)):
    wl = db.query(models.PhoneWhitelist).filter(models.PhoneWhitelist.id == wl_id).first()
    if wl:
        linked = db.query(models.User).filter(models.User.phone == wl.phone).first()
        if linked and linked.id != user.get("id"):
            db.delete(linked)
        db.delete(wl)
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/reset-password")
async def reset_password(user_id: int, request: Request, db: Session = Depends(get_db),
                         user: dict = Depends(require_admin)):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if u:
        u.password_hash = None
        u.session_version = (u.session_version or 1) + 1
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/admin/audit", response_class=HTMLResponse)
async def audit_log(request: Request, db: Session = Depends(get_db),
                    user: dict = Depends(require_login),
                    user_filter: str = "", limit: int = 200):
    if not _is_audit_allowed(user):
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
async def audit_clear(request: Request, db: Session = Depends(get_db),
                      user: dict = Depends(require_login)):
    if not _is_audit_allowed(user):
        return RedirectResponse("/", status_code=302)
    db.query(models.AuditLog).delete()
    db.commit()
    return RedirectResponse("/admin/audit", status_code=303)


# ─── VPK Criteria Admin ───────────────────────────────────────────────────────

@router.get("/admin/vpk-criteria", response_class=HTMLResponse)
async def vpk_criteria_admin(request: Request, db: Session = Depends(get_db),
                              user: dict = Depends(require_admin)):
    c1 = db.query(models.VpkCriterion).filter(
        models.VpkCriterion.vpk_type == 1).order_by(models.VpkCriterion.order).all()
    c2 = db.query(models.VpkCriterion).filter(
        models.VpkCriterion.vpk_type == 2).order_by(models.VpkCriterion.order).all()
    return templates.TemplateResponse("admin_vpk_criteria.html", {
        "request": request, "user": user,
        "criteria1": c1, "criteria2": c2,
        "msg": request.query_params.get("msg"),
    })


@router.post("/admin/vpk-criteria/add")
async def vpk_criteria_add(request: Request, db: Session = Depends(get_db),
                            user: dict = Depends(require_admin),
                            name: str = Form(...), vpk_type: int = Form(...)):
    last = db.query(models.VpkCriterion).filter(
        models.VpkCriterion.vpk_type == vpk_type
    ).order_by(models.VpkCriterion.order.desc()).first()
    new_order = (last.order + 1) if last else 1
    db.add(models.VpkCriterion(name=name.strip(), vpk_type=vpk_type, order=new_order))
    db.commit()
    return RedirectResponse("/admin/vpk-criteria?msg=Критерий добавлен", status_code=303)


@router.post("/admin/vpk-criteria/{crit_id}/edit")
async def vpk_criteria_edit(crit_id: int, request: Request,
                             db: Session = Depends(get_db),
                             user: dict = Depends(require_admin),
                             name: str = Form(...)):
    c = db.query(models.VpkCriterion).filter(models.VpkCriterion.id == crit_id).first()
    if c:
        c.name = name.strip()
        db.commit()
    return RedirectResponse("/admin/vpk-criteria?msg=Сохранено", status_code=303)


@router.post("/admin/vpk-criteria/{crit_id}/delete")
async def vpk_criteria_delete(crit_id: int, request: Request,
                               db: Session = Depends(get_db),
                               user: dict = Depends(require_admin)):
    c = db.query(models.VpkCriterion).filter(models.VpkCriterion.id == crit_id).first()
    if c:
        db.delete(c)
        db.commit()
    return RedirectResponse("/admin/vpk-criteria?msg=Удалено", status_code=303)


@router.post("/api/admin/vpk-criteria/reorder")
async def vpk_criteria_reorder(request: Request, db: Session = Depends(get_db)):
    """AJAX: принимает [{id, order}, ...] и сохраняет порядок."""
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return {"error": "forbidden"}
    data = await request.json()
    for item in data:
        c = db.query(models.VpkCriterion).filter(
            models.VpkCriterion.id == item["id"]).first()
        if c:
            c.order = item["order"]
    db.commit()
    return {"ok": True}


# ─── Database Backup ──────────────────────────────────────────────────────────

@router.get("/admin/backup")
async def db_backup(request: Request, db: Session = Depends(get_db),
                    user: dict = Depends(require_admin)):
    """Скачать дамп PostgreSQL (только для is_admin). Используется pg_dump."""
    import io
    import os
    import subprocess
    from datetime import date

    from fastapi.responses import Response as _Resp

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or "postgresql" not in db_url:
        return HTMLResponse("<h3>Backup доступен только для PostgreSQL</h3>", status_code=400)

    try:
        result = subprocess.run(
            ["pg_dump", "--no-password", "--format=plain", db_url],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            return HTMLResponse(
                f"<h3>pg_dump ошибка:</h3><pre>{result.stderr.decode()}</pre>",
                status_code=500)
        fname = f"lenta_backup_{date.today().isoformat()}.sql"
        return _Resp(
            content=result.stdout,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )
    except FileNotFoundError:
        return HTMLResponse(
            "<h3>pg_dump не найден на сервере</h3>"
            "<p>На Railway pg_dump доступен в buildpack-окружении. "
            "Альтернатива: Railway Dashboard → Postgres → Backups (ручной snapshot).</p>",
            status_code=500)
