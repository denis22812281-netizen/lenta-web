"""Реконструкции, Констракшн — список проектов + импорт + очистка."""
from datetime import date

from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse

from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, require_login
from config import STATUSES
from services.excel_import import import_reconstruct_excel, import_construction_excel
from utils.files import read_limited

router = APIRouter()


def _section_response(request, user, q_type, title, icon, color, url, db):
    request_obj = request
    manager_id = request_obj.query_params.get("manager_id")
    status     = request_obj.query_params.get("status")
    search     = request_obj.query_params.get("search")
    q = db.query(models.Project).filter(models.Project.project_type == q_type)
    if manager_id and str(manager_id).isdigit():
        q = q.filter(models.Project.manager_id == int(manager_id))
    if status:
        q = q.filter(models.Project.status == status)
    if search:
        q = q.filter(models.Project.tk_number.contains(search))
    projects = q.order_by(models.Project.end_date.nullslast()).all()
    managers = db.query(models.Manager).all()
    return templates.TemplateResponse("section_projects.html", {
        "request": request, "user": user,
        "section_title": title, "section_icon": icon,
        "section_color": color, "section_type": q_type, "section_url": url,
        "projects": projects, "managers": managers,
        "statuses": STATUSES, "today": date.today(),
        "filter_manager_id": manager_id, "filter_status": status, "search": search or "",
    })


@router.get("/reconstruct", response_class=HTMLResponse)
async def reconstruct_view(request: Request, db: Session = Depends(get_db),
                           user: dict = Depends(require_login)):
    return _section_response(request, user, "Реконструкция",
                              "Реконструкции", "bi-building-fill", "red", "/reconstruct", db)


@router.get("/construction", response_class=HTMLResponse)
async def construction_view(request: Request, db: Session = Depends(get_db),
                            user: dict = Depends(require_login)):
    return _section_response(request, user, "Констракшн",
                              "Констракшн", "bi-buildings-fill", "blue", "/construction", db)


# ─── Специализированный импорт ────────────────────────────────────────────────

@router.get("/import-reconstruct", response_class=HTMLResponse)
async def import_reconstruct_page(request: Request, user: dict = Depends(require_login)):
    return templates.TemplateResponse("import_reconstruct.html", {
        "request": request, "user": user,
        "section_title": "Реконструкции",
        "form_action": "/import-reconstruct",
        "file_accept": ".xlsx,.xls",
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
    })


_MAX_EXCEL_MB = 10
_MAX_EXCEL_BYTES = _MAX_EXCEL_MB * 1024 * 1024


@router.post("/import-reconstruct")
async def do_import_reconstruct(request: Request, db: Session = Depends(get_db),
                                 user: dict = Depends(require_login),
                                 file: UploadFile = File(...)):
    try:
        content = await read_limited(file, _MAX_EXCEL_BYTES)
    except ValueError:
        return RedirectResponse(
            f"/import-reconstruct?error=Файл слишком большой (макс {_MAX_EXCEL_MB} МБ)",
            status_code=303)
    try:
        result = import_reconstruct_excel(content, db)
        return RedirectResponse(
            f"/import-reconstruct?msg=Импорт завершён: создано {result['created']}, обновлено {result['updated']} проектов",
            status_code=303)
    except Exception as e:
        return RedirectResponse(f"/import-reconstruct?error={str(e)[:120]}", status_code=303)


@router.get("/import-construction", response_class=HTMLResponse)
async def import_construction_page(request: Request, user: dict = Depends(require_login)):
    return templates.TemplateResponse("import_reconstruct.html", {
        "request": request, "user": user,
        "section_title": "Констракшн",
        "form_action": "/import-construction",
        "file_accept": ".xlsx,.xls,.xlsm",
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
    })


@router.post("/import-construction")
async def do_import_construction(request: Request, db: Session = Depends(get_db),
                                  user: dict = Depends(require_login),
                                  file: UploadFile = File(...)):
    try:
        content = await read_limited(file, _MAX_EXCEL_BYTES)
    except ValueError:
        return RedirectResponse(
            f"/import-construction?error=Файл слишком большой (макс {_MAX_EXCEL_MB} МБ)",
            status_code=303)
    try:
        result = import_construction_excel(content, db)
        msg = (f"Создано:{result['created']} Обновлено:{result['updated']} "
               f"Строк:{result.get('rows_with_tk',0)} "
               f"Форматы:[{','.join(result.get('sample_formats',[]))}] "
               f"Менеджеры:[{','.join(result.get('sample_managers',[]))}]")
        return RedirectResponse(f"/import-construction?msg={msg}", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/import-construction?error={str(e)[:120]}", status_code=303)


# ─── Административные операции очистки (только admin) ────────────────────────

@router.post("/projects/clear-all")
async def clear_all_projects(request: Request, db: Session = Depends(get_db),
                              user: dict = Depends(require_login)):
    if not user.get("is_admin"):
        return RedirectResponse("/", status_code=302)
    for p in db.query(models.Project).filter(
            models.Project.project_type.in_(["Реконструкция", "Констракшн"])).all():
        db.delete(p)
    db.commit()
    return RedirectResponse("/?msg=Все проекты удалены", status_code=303)


@router.post("/construction/clear-all")
async def clear_all_construction(request: Request, db: Session = Depends(get_db),
                                  user: dict = Depends(require_login)):
    if not user.get("is_admin"):
        return RedirectResponse("/login", status_code=302)
    for p in db.query(models.Project).filter(
            models.Project.project_type == "Констракшн").all():
        db.delete(p)
    db.commit()
    return RedirectResponse(
        "/construction?msg=Все проекты Констракшн удалены. Загрузите файл заново.",
        status_code=303)


@router.post("/construction/delete-non-2026")
async def delete_construction_non_2026(request: Request, db: Session = Depends(get_db),
                                        user: dict = Depends(require_login)):
    if not user.get("is_admin"):
        return RedirectResponse("/login", status_code=302)
    from datetime import date as date_cls
    d1 = db.query(models.Project).filter(
        models.Project.project_type == "Констракшн",
        models.Project.end_date != None,
        models.Project.end_date < date_cls(2026, 1, 1),
    ).delete()
    d2 = db.query(models.Project).filter(
        models.Project.project_type == "Констракшн",
        models.Project.opening_date != None,
        models.Project.opening_date < date_cls(2026, 1, 1),
    ).delete()
    db.commit()
    return RedirectResponse(
        f"/construction?msg=Удалено объектов 2025 года: {d1 + d2}", status_code=303)


@router.post("/reconstruct/delete-tk-prefix")
async def delete_tk_prefix(request: Request, db: Session = Depends(get_db),
                            user: dict = Depends(require_login)):
    if not user.get("is_admin"):
        return RedirectResponse("/login", status_code=302)
    projects = db.query(models.Project).filter(
        models.Project.project_type == "Реконструкция",
        models.Project.tk_number.op("~")("^(ТК|TK|L)")
    ).all()
    count = len(projects)
    for p in projects:
        db.delete(p)
    db.commit()
    return RedirectResponse(f"/reconstruct?msg=Удалено: {count} проектов", status_code=303)
