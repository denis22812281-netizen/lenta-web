from fastapi import Request, HTTPException
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")


def get_current_user(request: Request):
    return request.session.get("user")


def require_login(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user
