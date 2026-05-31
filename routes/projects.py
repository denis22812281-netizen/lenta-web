"""All project-related routes: list, detail, create, update, delete, stages, excel import/export."""
import io
from datetime import datetime, date

from fastapi import APIRouter, Request, Form, Depends, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment

import models
from database import get_db
from deps import templates, get_current_user
from config import PROJECT_TYPES, STATUSES, STAGE_NAMES
from services.excel_import import parse_excel_file

router = APIRouter()


# ─── Список всех проектов ────────────────────────────────────────────────────

@router.get("/projects", response_class=HTMLResponse)
async def projects_list(request: Request, db: Session = Depends(get_db),
                        manager_id: str = None, status: str = None,
                        project_type: str = None, search: str = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    q = db.query(models.Project)
    if manager_id and str(manager_id).isdigit():
        q = q.filter(models.Project.manager_id == int(manager_id))
    if status:
        q = q.filter(models.Project.status == status)
    if project_type:
        q = q.filter(models.Project.project_type == project_type)
    if search:
        q = q.filter(models.Project.tk_number.contains(search))
    projects = q.order_by(models.Project.end_date.nullslast()).all()
    managers = db.query(models.Manager).all()
    return templates.TemplateResponse("projects.html", {
        "request": request, "user": user,
        "projects": projects, "managers": managers,
        "project_types": PROJECT_TYPES, "statuses": STATUSES, "today": date.today(),
        "filter_manager_id": manager_id, "filter_status": status,
        "filter_type": project_type, "search": search or "",
    })


@router.post("/projects/create")
async def create_project(request: Request, db: Session = Depends(get_db),
                         name: str = Form(...), tk_number: str = Form(""),
                         city: str = Form(""), project_type: str = Form(""),
                         manager_id: str = Form(""), status: str = Form("Активный"),
                         stage: str = Form(""), start_date: str = Form(""),
                         end_date: str = Form(""), description: str = Form(""),
                         budget: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    db.add(models.Project(
        name=name, tk_number=tk_number, city=city, project_type=project_type,
        manager_id=int(manager_id) if manager_id else None,
        status=status, stage=stage, description=description,
        start_date=datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None,
        end_date=datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None,
        budget=float(budget.replace(",", ".")) if budget else None,
    ))
    db.commit()
    return RedirectResponse("/projects", status_code=303)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404)
    managers = db.query(models.Manager).all()
    return templates.TemplateResponse("project_detail.html", {
        "request": request, "user": user,
        "project": project, "managers": managers,
        "project_types": PROJECT_TYPES, "statuses": STATUSES,
        "stage_names": STAGE_NAMES, "today": date.today(),
    })


@router.post("/projects/{project_id}/update")
async def update_project(project_id: int, request: Request, db: Session = Depends(get_db),
                         name: str = Form(...), tk_number: str = Form(""),
                         city: str = Form(""), project_type: str = Form(""),
                         manager_id: str = Form(""), status: str = Form("Активный"),
                         stage: str = Form(""), start_date: str = Form(""),
                         end_date: str = Form(""), description: str = Form(""),
                         budget: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    p = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404)
    p.name = name; p.tk_number = tk_number; p.city = city
    p.project_type = project_type; p.status = status; p.stage = stage
    p.manager_id = int(manager_id) if manager_id else None
    p.start_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    p.end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
    p.description = description
    p.budget = float(budget.replace(",", ".")) if budget else None
    db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@router.post("/projects/{project_id}/delete")
async def delete_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    p = db.query(models.Project).filter(models.Project.id == project_id).first()
    if p:
        db.delete(p)
        db.commit()
    return RedirectResponse("/projects", status_code=303)


# ─── Этапы проекта ────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/stages/add")
async def add_stage(project_id: int, request: Request, db: Session = Depends(get_db),
                    name: str = Form(...), start_date: str = Form(""),
                    end_date: str = Form(""), stage_status: str = Form("Запланировано")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    order = db.query(models.ProjectStage).filter(
        models.ProjectStage.project_id == project_id).count()
    db.add(models.ProjectStage(
        project_id=project_id, name=name, status=stage_status,
        start_date=datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None,
        end_date=datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None,
        order=order,
    ))
    db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@router.post("/stages/{stage_id}/delete")
async def delete_stage(stage_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    s = db.query(models.ProjectStage).filter(models.ProjectStage.id == stage_id).first()
    project_id = s.project_id if s else None
    if s:
        db.delete(s)
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


# ─── Создание проекта из секции (Реконструкции / Констракшн) ──────────────────

@router.post("/section/create-project")
async def section_create_project(request: Request, db: Session = Depends(get_db),
                                  name: str = Form(...), tk_number: str = Form(""),
                                  city: str = Form(""), project_type: str = Form(...),
                                  manager_id: str = Form(""), status: str = Form("Активный"),
                                  stage: str = Form(""), start_date: str = Form(""),
                                  end_date: str = Form(""), description: str = Form(""),
                                  budget: str = Form(""), redirect_to: str = Form("/")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    db.add(models.Project(
        name=name, tk_number=tk_number, city=city, project_type=project_type,
        manager_id=int(manager_id) if manager_id else None,
        status=status, stage=stage, description=description,
        start_date=datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None,
        end_date=datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None,
        budget=float(budget.replace(",", ".")) if budget else None,
    ))
    db.commit()
    return RedirectResponse(redirect_to, status_code=303)


# ─── Excel импорт/экспорт ─────────────────────────────────────────────────────

@router.post("/projects/import-excel")
async def import_excel(request: Request, db: Session = Depends(get_db),
                       file: UploadFile = File(...), manager_id: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    content = await file.read()
    try:
        result = parse_excel_file(content, "", int(manager_id) if manager_id else None, db)
    except Exception:
        return RedirectResponse("/projects?error=invalid_excel", status_code=303)
    return RedirectResponse("/projects", status_code=303)


@router.post("/import-excel-section")
async def import_excel_section(request: Request, db: Session = Depends(get_db),
                                file: UploadFile = File(...),
                                project_type: str = Form(""),
                                manager_id: str = Form(""),
                                redirect_to: str = Form("/")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    content = await file.read()
    try:
        result = parse_excel_file(content, project_type,
                                  int(manager_id) if manager_id else None, db)
        return RedirectResponse(
            f"{redirect_to}?msg=created:{result['created']},updated:{result['updated']}",
            status_code=303)
    except Exception as e:
        return RedirectResponse(f"{redirect_to}?error={str(e)[:80]}", status_code=303)


@router.get("/api/export/projects-excel")
async def export_excel(db: Session = Depends(get_db), type: str = None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Проекты"
    hfill  = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    hfont  = Font(color="FFFFFF", bold=True, size=11)
    center = Alignment(horizontal="center", vertical="center")
    headers = ["№", "ТК №", "Название проекта", "Город", "Тип", "Менеджер",
               "Статус", "Этап", "Дата начала", "Дата окончания", "Бюджет, руб."]
    ws.row_dimensions[1].height = 20
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.fill = hfill; c.font = hfont; c.alignment = center

    q = db.query(models.Project)
    if type:
        q = q.filter(models.Project.project_type == type)
    today = date.today()
    for i, p in enumerate(q.all(), 2):
        ws.cell(row=i, column=1, value=i - 1)
        ws.cell(row=i, column=2, value=p.tk_number)
        ws.cell(row=i, column=3, value=p.name)
        ws.cell(row=i, column=4, value=p.city)
        ws.cell(row=i, column=5, value=p.project_type)
        ws.cell(row=i, column=6, value=p.manager.name if p.manager else "")
        ws.cell(row=i, column=7, value=p.status)
        ws.cell(row=i, column=8, value=p.stage)
        ws.cell(row=i, column=9, value=p.start_date)
        ws.cell(row=i, column=10, value=p.end_date)
        ws.cell(row=i, column=11, value=p.budget)
        if p.end_date:
            days = (p.end_date - today).days
            color = "FFCCCC" if days < 0 else "FFEB9C" if days <= 7 else "D4EDDA"
            rf = PatternFill(start_color=color, end_color=color, fill_type="solid")
            for col in range(1, 12):
                ws.cell(row=i, column=col).fill = rf

    for col, w in enumerate([4, 8, 40, 15, 18, 18, 14, 20, 14, 14, 15], 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=lenta_projects.xlsx"},
    )
