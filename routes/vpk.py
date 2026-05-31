import io
from datetime import datetime, date, timedelta
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user
from services.email_service import notify_vpk_report

router = APIRouter()


# ─── ВПК ─────────────────────────────────────────────────────────────────────

@router.get("/vpk", response_class=HTMLResponse)
async def vpk_page(request: Request, db: Session = Depends(get_db), tab: str = "vpk1"):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    projects  = db.query(models.Project).filter(
        models.Project.project_type == "Констракшн").order_by(models.Project.tk_number).all()
    criteria1 = db.query(models.VpkCriterion).filter(
        models.VpkCriterion.vpk_type == 1).order_by(models.VpkCriterion.order).all()
    criteria2 = db.query(models.VpkCriterion).filter(
        models.VpkCriterion.vpk_type == 2).order_by(models.VpkCriterion.order).all()
    reports   = db.query(models.VpkReport).order_by(
        models.VpkReport.submitted_at.desc()).limit(50).all()
    name = user.get("display_name", "")
    unread = 0
    if "Гаврин" in name:
        unread = db.query(models.VpkReport).filter(models.VpkReport.read_gavrin == False).count()
    elif "Месмер" in name:
        unread = db.query(models.VpkReport).filter(models.VpkReport.read_mesmer == False).count()
    return templates.TemplateResponse("vpk.html", {
        "request": request, "user": user,
        "tab": tab, "projects": projects,
        "criteria1": criteria1, "criteria2": criteria2,
        "reports": reports, "unread": unread,
        "msg": request.query_params.get("msg"),
    })


@router.post("/vpk/submit")
async def vpk_submit(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
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
    photo_dir = Path("static/uploads/vpk")
    photo_dir.mkdir(parents=True, exist_ok=True)
    for c in criteria:
        done    = form.get(f"criterion_{c.id}") == "on"
        comment = str(form.get(f"comment_{c.id}", "") or "").strip()
        photo_path = ""
        photo_file = form.get(f"photo_{c.id}")
        if photo_file and hasattr(photo_file, "filename") and photo_file.filename:
            ext = Path(photo_file.filename).suffix.lower() or ".jpg"
            fname = f"{report.id}_{c.id}{ext}"
            (photo_dir / fname).write_bytes(await photo_file.read())
            photo_path = f"uploads/vpk/{fname}"
        db.add(models.VpkReportItem(
            report_id=report.id, criterion_id=c.id,
            criterion_name=c.name, done=done,
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
    for mgr in db.query(models.Manager).filter(
            models.Manager.email != "", models.Manager.email.isnot(None)).all():
        if mgr.is_leader or (proj and proj.manager_id == mgr.id):
            recipients[mgr.email] = mgr.name

    for email, name in recipients.items():
        notify_vpk_report(
            to_email=email, recipient_name=name,
            vpk_type=vpk_type, tk_number=tk, project_name=proj_name,
            submitted_by=submitter, done=done, total=total,
            submitted_at=submitted_at, failed_items=failed_items,
        )

    return RedirectResponse(
        f"/vpk?tab=reports&msg=Отчёт ВПК{vpk_type} по ТК {tk} отправлен",
        status_code=303)


@router.post("/vpk/reports/{report_id}/read")
async def vpk_mark_read(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"error": "Не авторизован"}
    report = db.query(models.VpkReport).filter(models.VpkReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404)
    name = user.get("display_name", "")
    if "Гаврин" in name:
        report.read_gavrin = True
    elif "Месмер" in name:
        report.read_mesmer = True
    db.commit()
    return {"ok": True}


@router.get("/api/vpk/unread")
async def vpk_unread(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"reports": []}
    name = user.get("display_name", "")
    if "Гаврин" in name:
        reports = db.query(models.VpkReport).filter(models.VpkReport.read_gavrin == False).all()
    elif "Месмер" in name:
        reports = db.query(models.VpkReport).filter(models.VpkReport.read_mesmer == False).all()
    else:
        return {"reports": []}
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
                       vpk_type: str = "", manager_name: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
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
                         date_from: str = "", date_to: str = "", vpk_type: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
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
async def clear_all_reports(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse("/reports", status_code=302)
    db.query(models.VpkReportItem).delete()
    db.query(models.VpkReport).delete()
    db.commit()
    return RedirectResponse("/reports", status_code=303)
