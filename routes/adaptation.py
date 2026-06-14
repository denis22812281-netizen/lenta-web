"""Карточка адаптации — список, форма, сохранение, отправка, скачивание Excel."""
import io
import json
import os
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import require_admin, require_login, templates
from services.adaptation import FIELDS, DROPDOWN_OPTIONS, generate_excel, TEMPLATE_PATH

router = APIRouter()

_NOTIFY_EMAIL = os.getenv("NOTIFY_PRECHECK_EMAIL", "denis.mesmer@lenta.com")


# ── helpers ──────────────────────────────────────────────────────────────────

def _send_adaptation_email(card: models.AdaptationCard) -> None:
    """Send adaptation card by email with Excel attachment."""
    try:
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException
        cfg = sib_api_v3_sdk.Configuration()
        cfg.api_key["api-key"] = os.getenv("BREVO_API_KEY", "")
        api = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(cfg))

        excel_bytes = generate_excel(card.data or {})
        import base64
        attachment_b64 = base64.b64encode(excel_bytes).decode()

        tk = card.tk_number or "—"
        html = f"""
        <h2>Карточка адаптации — ТК {tk}</h2>
        <p>Составил: <b>{card.created_by}</b></p>
        <p>Дата: {card.created_at.strftime('%d.%m.%Y %H:%M')}</p>
        <p>Карточка прикреплена в формате Excel (.xlsx).</p>
        """

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": _NOTIFY_EMAIL, "name": "Denis Mesmer"}],
            sender={"email": "noreply@lenta-projects.ru", "name": "Lenta Projects"},
            subject=f"Карточка адаптации ТК {tk}",
            html_content=html,
            attachment=[{
                "content": attachment_b64,
                "name": f"adaptation_tk{tk}.xlsx",
            }],
        )
        api.send_transac_email(send_smtp_email)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("adaptation email error: %s", exc)


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

    # Collect all field values
    data: dict = {}
    for key, _cell, _label, _opts in FIELDS:
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
            created_by=user.get("name", ""),
            status="draft",
            data=data,
        )
        db.add(card)

    db.commit()
    db.refresh(card)
    return RedirectResponse(f"/adaptation/{card.id}/edit", status_code=303)


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

    card.status = "sent"
    card.sent_at = datetime.utcnow()
    card.recipient_email = _NOTIFY_EMAIL
    db.commit()

    background_tasks.add_task(_send_adaptation_email, card)
    return RedirectResponse(f"/adaptation/{card_id}/edit?sent=1", status_code=303)


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
