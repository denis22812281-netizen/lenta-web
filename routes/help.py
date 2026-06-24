from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from deps import get_current_user, templates

router = APIRouter()


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("help.html", {"request": request, "user": user})
