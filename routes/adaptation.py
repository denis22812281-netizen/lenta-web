"""Карточка адаптации — список, форма, сохранение, отправка, скачивание Excel."""
import io
import os
import tempfile
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import require_admin, require_login, templates
from services.adaptation import FIELDS, FREE_TEXT_SECTIONS, DROPDOWN_OPTIONS, generate_excel, TEMPLATE_PATH

router = APIRouter()

_NOTIFY_EMAIL = os.getenv("NOTIFY_PRECHECK_EMAIL", "denis.mesmer@lenta.com")


# ── helpers ──────────────────────────────────────────────────────────────────

def _send_adaptation_email(card_dict: dict) -> None:
    """Send adaptation card by email. Receives plain dict to avoid DetachedInstanceError."""
    import logging
    log = logging.getLogger(__name__)
    try:
        from services.email_service import notify_adaptation_card

        tk = card_dict.get("tk_number") or "—"
        author = card_dict.get("created_by") or "—"
        created_at = card_dict.get("created_at")
        if hasattr(created_at, "strftime"):
            date_str = created_at.strftime("%d.%m.%Y %H:%M")
        else:
            date_str = str(created_at or "")
        data = card_dict.get("data") or {}

        excel_bytes = generate_excel(data)

        # Write to temp file — email_service reads from path
        fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
        try:
            os.write(fd, excel_bytes)
            os.close(fd)
            notify_adaptation_card(
                to_email=_NOTIFY_EMAIL,
                tk_number=tk,
                author=author,
                date_str=date_str,
                data=data,
                excel_path=tmp_path,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).error("adaptation email error: %s", exc, exc_info=True)


# ── list ─────────────────────────────────────────────────────────────────────

@router.get("/adaptation", response_class=HTMLResponse)
async def adaptation_list(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    cards = (
        db.query(models.AdaptationCard)
        .order_by(models.AdaptationCard.created_at.desc())
        .all()
    )
    return templates.TemplateResponse("adaptation_list.html", {
        "request": request, "user": user, "cards": cards,
    })


# ── new card ─────────────────────────────────────────────────────────────────

@router.get("/adaptation/new", response_class=HTMLResponse)
async def adaptation_new(
    request: Request,
    user: dict = Depends(require_login),
):
    return templates.TemplateResponse("adaptation_form.html", {
        "request": request,
        "user": user,
        "card": None,
        "card_data": {},
        "fields": FIELDS,
        "dropdown_options": DROPDOWN_OPTIONS,
        "photos": [],
    })


# ── edit card ────────────────────────────────────────────────────────────────

@router.get("/adaptation/{card_id}/edit", response_class=HTMLResponse)
async def adaptation_edit(
    card_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    card = db.query(models.AdaptationCard).filter_by(id=card_id).first()
    if not card:
        return RedirectResponse("/adaptation", status_code=302)
    return templates.TemplateResponse("adaptation_form.html", {
        "request": request,
        "user": user,
        "card": card,
        "card_data": card.data or {},
        "fields": FIELDS,
        "dropdown_options": DROPDOWN_OPTIONS,
        "photos": card.photos if card else [],
    })


# ── save (draft) ─────────────────────────────────────────────────────────────

@router.post("/adaptation/save")
async def adaptation_save(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    form = await request.form()
    card_id = form.get("card_id", "").strip()
    tk_number = form.get("tk_number", "").strip()

    # Collect structured field values
    data: dict = {}
    for key, _cell, _label, _opts in FIELDS:
        v = form.get(key, "")
        if v:
            data[key] = v

    # Collect free-text section values (notes_main, notes_fasad, etc.)
    for key in FREE_TEXT_SECTIONS:
        v = form.get(key, "")
        if v:
            data[key] = v

    if card_id:
        card = db.query(models.AdaptationCard).filter_by(id=int(card_id)).first()
        if card:
            card.tk_number = tk_number
            card.data = data
            card.updated_at = datetime.utcnow()
    else:
        card = models.AdaptationCard(
            tk_number=tk_number,
            created_by=user.get("display_name", ""),
            status="draft",
            data=data,
        )
        db.add(card)

    db.commit()
    db.refresh(card)
    return RedirectResponse(f"/adaptation/{card.id}/edit?saved=1", status_code=303)


# ── send (email + mark sent) ─────────────────────────────────────────────────

@router.post("/adaptation/{card_id}/send")
async def adaptation_send(
    card_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    card = db.query(models.AdaptationCard).filter_by(id=card_id).first()
    if not card:
        return RedirectResponse("/adaptation", status_code=302)

    # Extract all data BEFORE commit — avoid DetachedInstanceError in background task
    card_dict = {
        "tk_number":  card.tk_number,
        "created_by": card.created_by,
        "created_at": card.created_at,
        "data":       dict(card.data or {}),
    }

    card.status = "sent"
    card.sent_at = datetime.utcnow()
    card.recipient_email = _NOTIFY_EMAIL
    db.commit()

    from services.email_service import EMAIL_ENABLED
    background_tasks.add_task(_send_adaptation_email, card_dict)
    suffix = "" if EMAIL_ENABLED else "&email_warn=1"
    return RedirectResponse(f"/adaptation/{card_id}/edit?sent=1{suffix}", status_code=303)


# ── delete card ──────────────────────────────────────────────────────────────

@router.post("/adaptation/{card_id}/delete")
async def adaptation_delete(
    card_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    card = db.query(models.AdaptationCard).filter_by(id=card_id).first()
    if card:
        db.delete(card)
        db.commit()
    return RedirectResponse("/adaptation?deleted=1", status_code=303)


# ── download Excel ───────────────────────────────────────────────────────────

@router.get("/adaptation/{card_id}/download")
async def adaptation_download(
    card_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    card = db.query(models.AdaptationCard).filter_by(id=card_id).first()
    if not card:
        return RedirectResponse("/adaptation", status_code=302)

    excel_bytes = generate_excel(card.data or {})
    tk = card.tk_number or str(card_id)
    filename = f"adaptation_tk{tk}.xlsx"
    filename_encoded = quote(filename)

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
        },
    )


# ── admin: upload new template ────────────────────────────────────────────────

@router.post("/adaptation/{card_id}/photos/upload")
async def adaptation_photo_upload(
    card_id: int, request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    card = db.query(models.AdaptationCard).filter_by(id=card_id).first()
    if not card:
        raise __import__('fastapi').HTTPException(status_code=404)
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        return RedirectResponse(f"/adaptation/{card_id}/edit#photos", status_code=303)
    from services.cloud_storage import upload_photo
    import uuid as _uuid
    from pathlib import Path as _Path
    ext = _Path(file.filename or "photo.jpg").suffix.lower() or ".jpg"
    fname = f"{_uuid.uuid4().hex[:10]}{ext}"
    url = upload_photo(content, f"adaptation/card-{card_id}", fname)
    db.add(models.AdaptationPhoto(
        card_id=card_id,
        photo_url=url,
        original_name=file.filename or fname,
        uploaded_by=user.get("display_name", ""),
    ))
    db.commit()
    return RedirectResponse(f"/adaptation/{card_id}/edit#photos", status_code=303)


@router.post("/adaptation/{card_id}/photos/{photo_id}/delete")
async def adaptation_photo_delete(
    card_id: int, photo_id: int, request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    ph = db.query(models.AdaptationPhoto).filter_by(id=photo_id, card_id=card_id).first()
    if ph and (user.get("is_admin") or ph.uploaded_by == user.get("display_name")):
        db.delete(ph)
        db.commit()
    return RedirectResponse(f"/adaptation/{card_id}/edit#photos", status_code=303)


@router.post("/admin/adaptation-template")
async def upload_adaptation_template(
    file: UploadFile = File(...),
    user: dict = Depends(require_admin),
):
    if not file.filename.endswith(".xlsx"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Только .xlsx файлы"}, status_code=400)

    content = await file.read()
    TEMPLATE_PATH.write_bytes(content)
    return RedirectResponse("/admin/users?template_updated=1", status_code=303)
