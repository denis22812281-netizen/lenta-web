from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from deps import templates

router = APIRouter()


@router.get("/case", response_class=HTMLResponse)
async def case_page(request: Request):
    return templates.TemplateResponse("case.html", {"request": request})
