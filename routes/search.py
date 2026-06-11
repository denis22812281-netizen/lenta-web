from datetime import date
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, require_login

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = "", db: Session = Depends(get_db),
                      user: dict = Depends(require_login)):
    results = {"projects": [], "managers": [], "tasks": []}
    if q and len(q.strip()) >= 2:
        like = f"%{q.strip()}%"

        results["projects"] = (
            db.query(models.Project)
            .filter(
                models.Project.tk_number.ilike(like) |
                models.Project.name.ilike(like) |
                models.Project.city.ilike(like) |
                models.Project.address.ilike(like)
            )
            .order_by(models.Project.end_date.nullslast())
            .limit(20).all()
        )

        results["managers"] = (
            db.query(models.Manager)
            .filter(models.Manager.name.ilike(like))
            .limit(10).all()
        )

        results["tasks"] = (
            db.query(models.Task)
            .filter(models.Task.title.ilike(like))
            .order_by(models.Task.deadline.nullslast())
            .limit(10).all()
        )

    total = sum(len(v) for v in results.values())
    return templates.TemplateResponse("search.html", {
        "request": request, "user": user,
        "q": q, "results": results, "total": total, "today": date.today(),
    })
