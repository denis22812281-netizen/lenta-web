from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user
from services.excel_import import parse_excel_file

router = APIRouter()


@router.get("/sync-settings", response_class=HTMLResponse)
async def sync_settings(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    configs = {cfg.project_type: cfg for cfg in db.query(models.SyncConfig).all()}
    return templates.TemplateResponse("sync_settings.html", {
        "request": request, "user": user,
        "configs": configs,
        "section_types": ["Реконструкция", "Констракшн", "КСО"],
    })


@router.post("/sync-settings/save")
async def save_sync_settings(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    form = await request.form()
    for ptype in ["Реконструкция", "Констракшн", "КСО"]:
        key = ptype.lower().replace(" ", "_")
        file_path = str(form.get(f"path_{key}", "")).strip()
        auto_sync = bool(form.get(f"auto_{key}"))
        interval  = int(form.get(f"interval_{key}", 60) or 60)
        cfg = db.query(models.SyncConfig).filter(
            models.SyncConfig.project_type == ptype).first()
        if cfg:
            cfg.file_path = file_path
            cfg.auto_sync = auto_sync
            cfg.sync_interval_minutes = interval
        else:
            db.add(models.SyncConfig(
                project_type=ptype, file_path=file_path,
                auto_sync=auto_sync, sync_interval_minutes=interval))
    db.commit()
    return RedirectResponse("/sync-settings?saved=1", status_code=303)


@router.post("/sync-settings/run-now")
async def run_sync_now(request: Request, db: Session = Depends(get_db),
                       project_type: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    cfg = db.query(models.SyncConfig).filter(
        models.SyncConfig.project_type == project_type).first()
    if cfg and cfg.file_path:
        path = Path(cfg.file_path)
        if path.exists():
            result = parse_excel_file(path.read_bytes(), project_type, None, db)
            cfg.last_synced = datetime.utcnow()
            cfg.last_status = f"OK: создано {result['created']}, обновлено {result['updated']}"
            db.commit()
        else:
            cfg.last_status = f"Файл не найден: {cfg.file_path}"
            db.commit()
    return RedirectResponse("/sync-settings?ran=1", status_code=303)
