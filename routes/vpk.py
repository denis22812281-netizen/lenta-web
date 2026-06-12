import io
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user, require_login
from services.email_service import notify_vpk_report, notify_precheck_report
from services.cloud_storage import upload_photo

import logging as _logging
_vpk_logger = _logging.getLogger(__name__)

# Список email для VPK-уведомлений. Формат: email:Имя,email2:Имя2
_VPK_NOTIFY_EMAILS = []
for _entry in os.getenv("NOTIFY_VPK_EMAILS", "").split(","):
    _entry = _entry.strip()
    if not _entry:
        continue
    if ":" in _entry:
        _e, _n = _entry.split(":", 1)
        _VPK_NOTIFY_EMAILS.append((_e.strip(), _n.strip()))
    else:
        _VPK_NOTIFY_EMAILS.append((_entry, _entry.split("@")[0]))
_vpk_logger.warning("VPK: NOTIFY_VPK_EMAILS = %s", _VPK_NOTIFY_EMAILS)

# Email для предосмотра — только один получатель (менеджер/куратор)
_PRECHECK_EMAIL = os.getenv("NOTIFY_PRECHECK_EMAIL", "").strip()

router = APIRouter()


# ─── ВПК ─────────────────────────────────────────────────────────────────────

@router.get("/vpk", response_class=HTMLResponse)
async def vpk_page(request: Request, db: Session = Depends(get_db),
                   user: dict = Depends(require_login), tab: str = "vpk1"):
    projects  = db.query(models.Project).filter(
        models.Project.project_type == "Констракшн").order_by(models.Project.tk_number).all()
    criteria1 = db.query(models.VpkCriterion).filter(
        models.VpkCriterion.vpk_type == 1).order_by(models.VpkCriterion.order).all()
    criteria2 = db.query(models.VpkCriterion).filter(
        models.VpkCriterion.vpk_type == 2).order_by(models.VpkCriterion.order).all()
    reports   = db.query(models.VpkReport).order_by(
        models.VpkReport.submitted_at.desc()).limit(50).all()
    pre_reports = db.query(models.PreVpkReport).order_by(
        models.PreVpkReport.submitted_at.desc()).limit(20).all()
    name = user.get("display_name", "")
    total_reports = db.query(models.VpkReport).count()
    read_by_me = db.query(models.VpkReportRead).filter(
        models.VpkReportRead.reader_name == name).count()
    unread = max(0, total_reports - read_by_me)
    vpk_t = int(request.query_params.get("vpk_t", 1))
    precheck_criteria = criteria1 if vpk_t == 1 else criteria2
    return templates.TemplateResponse("vpk.html", {
        "request": request, "user": user,
        "tab": tab, "projects": projects,
        "criteria1": criteria1, "criteria2": criteria2,
        "reports": reports, "unread": unread,
        "pre_reports": pre_reports,
        "vpk_t": vpk_t,
        "precheck_criteria": precheck_criteria,
        "msg": request.query_params.get("msg"),
    })


@router.post("/vpk/submit")
async def vpk_submit(request: Request, background_tasks: BackgroundTasks,
                     db: Session = Depends(get_db), user: dict = Depends(require_login)):
    form      = await request.form()
    project_id = form.get("project_id")
    vpk_type   = int(form.get("vpk_type", 1))
    report = models.VpkReport(
        project_id=int(project_id) if project_id else None,
        vpk_type=vpk_type,
        submitted_by=user.get("display_name", ""),
        read_gavrin=False, read_mesmer=False,
    )
    db.add(report)
    db.flush()
    criteria = db.query(models.VpkCriterion).filter(
        models.VpkCriterion.vpk_type == vpk_type
    ).order_by(models.VpkCriterion.order).all()
    for c in criteria:
        is_done = form.get(f"criterion_{c.id}") == "on"
        comment = str(form.get(f"comment_{c.id}", "") or "").strip()
        photo_path = ""
        photo_file = form.get(f"photo_{c.id}")
        if photo_file and hasattr(photo_file, "filename") and photo_file.filename:
            ext = Path(photo_file.filename).suffix.lower() or ".jpg"
            fname = f"{report.id}_{c.id}{ext}"
            photo_path = upload_photo(await photo_file.read(), "vpk", fname)
        db.add(models.VpkReportItem(
            report_id=report.id, criterion_id=c.id,
            criterion_name=c.name, done=is_done,
            comment=comment, photo_path=photo_path,
        ))
    db.commit()
    proj = db.query(models.Project).filter(models.Project.id == project_id).first()
    tk   = proj.tk_number if proj else "—"
    proj_name = proj.name if proj else ""

    # Email-уведомления — всем кто имеет email: лидеры + менеджер проекта
    items        = db.query(models.VpkReportItem).filter(
        models.VpkReportItem.report_id == report.id).all()
    done         = sum(1 for i in items if i.done)
    total        = len(items)
    submitted_at = report.submitted_at.strftime("%d.%m.%Y %H:%M") if report.submitted_at else ""
    submitter    = user.get("display_name", "")
    failed_items = [
        {"name": i.criterion_name, "comment": i.comment or "", "photo_path": i.photo_path or ""}
        for i in items if not i.done
    ]

    recipients = {}
    # Получатели: лидеры (Гаврин, Комаров) + отправитель + менеджер проекта
    for mgr in db.query(models.Manager).filter(
            models.Manager.email != "", models.Manager.email.isnot(None)).all():
        if mgr.is_leader or mgr.name == submitter or (proj and proj.manager_id == mgr.id):
            recipients[mgr.email] = mgr.name

    _vpk_logger.info("VPK submit: отправка email получателям %s", list(recipients.keys()))

    def _send_emails():
        for email, name in recipients.items():
            notify_vpk_report(
                to_email=email, recipient_name=name,
                vpk_type=vpk_type, tk_number=tk, project_name=proj_name,
                submitted_by=submitter, done=done, total=total,
                submitted_at=submitted_at, failed_items=failed_items,
            )

    background_tasks.add_task(_send_emails)

    return RedirectResponse(
        f"/vpk?tab=reports&msg=Отчёт ВПК{vpk_type} по ТК {tk} отправлен",
        status_code=303)


@router.post("/vpk/precheck")
async def precheck_submit(request: Request, background_tasks: BackgroundTasks,
                          db: Session = Depends(get_db), user: dict = Depends(require_login)):
    form      = await request.form()
    project_id = form.get("project_id")
    vpk_type   = int(form.get("vpk_type", 1))

    report = models.PreVpkReport(
        project_id=int(project_id) if project_id else None,
        vpk_type=vpk_type,
        submitted_by=user.get("display_name", ""),
    )
    db.add(report)
    db.flush()

    criteria = db.query(models.VpkCriterion).filter(
        models.VpkCriterion.vpk_type == vpk_type
    ).order_by(models.VpkCriterion.order).all()

    _all_keys = [k for k, v in form.multi_items() if isinstance(v, str)]
    _vpk_logger.warning("PRECHECK all_keys(%d): %s", len(_all_keys), _all_keys[:30])
    _vpk_logger.warning("PRECHECK form: project_id=%r tk_text=%r",
                        project_id, form.get("tk_text"))
    precheck_json = str(form.get("precheck_json", "{}") or "{}")
    try:
        precheck_states = json.loads(precheck_json)
    except Exception:
        precheck_states = {}
    _vpk_logger.warning("PRECHECK JSON received (%d keys): %s",
                        len(precheck_states), precheck_states)

    for c in criteria:
        state_val = precheck_states.get(str(c.id), "not_checked")
        status = state_val if state_val in ("done", "not_done", "not_checked") else "not_checked"
        comment = str(form.get(f"comment_{c.id}", "") or "").strip()
        photo_path = ""
        if status == "not_done":
            photo_file = form.get(f"photo_{c.id}")
            if photo_file and hasattr(photo_file, "filename") and photo_file.filename:
                ext = Path(photo_file.filename).suffix.lower() or ".jpg"
                fname = f"pre_{report.id}_{c.id}{ext}"
                photo_path = upload_photo(await photo_file.read(), "precheck", fname)
        db.add(models.PreVpkReportItem(
            report_id=report.id, criterion_id=c.id,
            criterion_name=c.name, status=status,
            comment=comment, photo_path=photo_path,
        ))

    db.commit()

    if project_id:
        proj = db.query(models.Project).filter(models.Project.id == int(project_id)).first()
    else:
        tk_text = str(form.get("tk_text", "") or "").strip()
        proj = db.query(models.Project).filter(models.Project.tk_number == tk_text).first() if tk_text else None
    tk   = proj.tk_number if proj else "—"
    proj_name = proj.name if proj else ""
    vpk_date_str = proj.vpk_date.strftime("%d.%m.%Y") if (proj and proj.vpk_date) else ""

    items       = db.query(models.PreVpkReportItem).filter(
        models.PreVpkReportItem.report_id == report.id).all()
    failed_items = [
        {"name": i.criterion_name, "comment": i.comment or "", "photo_path": i.photo_path or ""}
        for i in items if i.status == "not_done"
    ]
    ok_count   = sum(1 for i in items if i.status == "done")
    skip_count = sum(1 for i in items if i.status == "not_checked")

    # Получатель: env var → иначе email отправителя из таблицы менеджеров
    to_email = _PRECHECK_EMAIL
    if not to_email:
        submitter_name = user.get("display_name", "")
        mgr = db.query(models.Manager).filter(
            models.Manager.name == submitter_name,
            models.Manager.email.isnot(None),
            models.Manager.email != "",
        ).first()
        if mgr:
            to_email = mgr.email

    submitter = user.get("display_name", "")
    if to_email:
        background_tasks.add_task(
            notify_precheck_report, to_email, vpk_type, tk, proj_name,
            submitter, vpk_date_str, failed_items, ok_count, skip_count,
        )
    else:
        _vpk_logger.warning("Precheck: email не отправлен — NOTIFY_PRECHECK_EMAIL не задан и у менеджера нет email")

    return RedirectResponse(
        f"/vpk?tab=precheck&msg=Предосмотр ВПК{vpk_type} по ТК {tk} отправлен",
        status_code=303,
    )


@router.post("/vpk/reports/{report_id}/read")
async def vpk_mark_read(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"error": "Не авторизован"}
    report = db.query(models.VpkReport).filter(models.VpkReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404)
    name = user.get("display_name", "")
    existing = db.query(models.VpkReportRead).filter(
        models.VpkReportRead.report_id == report_id,
        models.VpkReportRead.reader_name == name,
    ).first()
    if not existing:
        db.add(models.VpkReportRead(report_id=report_id, reader_name=name))
        db.commit()
    return {"ok": True}


@router.get("/api/vpk/unread")
async def vpk_unread(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"reports": []}
    name = user.get("display_name", "")
    if not name:
        return {"reports": []}
    read_ids = {r.report_id for r in db.query(models.VpkReportRead).filter(
        models.VpkReportRead.reader_name == name).all()}
    reports = db.query(models.VpkReport).filter(
        models.VpkReport.id.notin_(read_ids)).all()
    result = []
    for r in reports:
        tk   = r.project.tk_number if r.project else "—"
        done = sum(1 for i in r.items if i.done)
        result.append({
            "id": r.id,
            "title": f"Новый отчёт ВПК{r.vpk_type} по ТК {tk}",
            "body": f"Подал: {r.submitted_by} | Выполнено: {done}/{len(r.items)} критериев",
        })
    return {"reports": result}


# ─── Отчёты ВПК ──────────────────────────────────────────────────────────────

@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, db: Session = Depends(get_db),
                       user: dict = Depends(require_login),
                       vpk_type: str = "", manager_name: str = ""):
    q = db.query(models.VpkReport).order_by(models.VpkReport.submitted_at.desc())
    if vpk_type in ("1", "2"):
        q = q.filter(models.VpkReport.vpk_type == int(vpk_type))
    if manager_name:
        q = q.filter(models.VpkReport.submitted_by == manager_name)
    reports = q.limit(100).all()
    authors = sorted({a[0] for a in db.query(models.VpkReport.submitted_by).distinct().all() if a[0]})
    return templates.TemplateResponse("reports.html", {
        "request": request, "user": user,
        "reports": reports, "authors": authors,
        "filter_vpk_type": vpk_type, "filter_manager": manager_name,
    })


@router.get("/reports/export")
async def reports_export(request: Request, db: Session = Depends(get_db),
                         user: dict = Depends(require_login),
                         date_from: str = "", date_to: str = "", vpk_type: str = ""):
    q = db.query(models.VpkReport).order_by(models.VpkReport.submitted_at.desc())
    if vpk_type in ("1", "2"):
        q = q.filter(models.VpkReport.vpk_type == int(vpk_type))
    if date_from:
        try:
            q = q.filter(models.VpkReport.submitted_at >=
                         datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(models.VpkReport.submitted_at <
                         datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            pass
    reports = q.all()
    wb = Workbook()
    ws = wb.active
    ws.title = "Отчёты ВПК"
    hfill  = PatternFill(start_color="1A5C22", end_color="1A5C22", fill_type="solid")
    hfont  = Font(color="FFFFFF", bold=True, size=12)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    wrap   = Alignment(vertical="center", wrap_text=True)
    headers    = ["Менеджер", "Номер ТК", "Критерий ВПК", "Комментарий"]
    col_widths = [25, 12, 60, 50]
    for col, (h, w) in enumerate(zip(headers, col_widths), 1):
        c = ws.cell(row=1, column=col, value=h)
        c.fill = hfill; c.font = hfont; c.alignment = center
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"
    row_num = 2
    for r in reports:
        tk  = r.project.tk_number if r.project else "—"
        mgr = r.project.manager.name if (r.project and r.project.manager) else "—"
        for item in r.items:
            ws.cell(row=row_num, column=1, value=mgr).alignment = wrap
            ws.cell(row=row_num, column=2, value=tk).alignment  = center
            ws.cell(row=row_num, column=3, value=item.criterion_name).alignment = wrap
            ws.cell(row=row_num, column=4, value=item.comment or "").alignment  = wrap
            ws.row_dimensions[row_num].height = 18
            row_num += 1
        row_num += 1
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    period = f"{date_from or 'all'}_{date_to or 'now'}"
    return StreamingResponse(output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=vpk_reports_{period}.xlsx"})


@router.post("/reports/clear-all")
async def clear_all_reports(request: Request, db: Session = Depends(get_db),
                             user: dict = Depends(require_login)):
    if not user.get("is_admin"):
        return RedirectResponse("/reports", status_code=302)
    db.query(models.VpkReportItem).delete()
    db.query(models.VpkReport).delete()
    db.commit()
    return RedirectResponse("/reports", status_code=303)
