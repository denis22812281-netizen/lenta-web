from fastapi import Request, HTTPException
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address

from utils.csrf import get_csrf_token

templates = Jinja2Templates(directory="templates")
templates.env.globals["csrf_token"] = get_csrf_token

# Rate limiter (shared между роутерами)
limiter = Limiter(key_func=get_remote_address)


def get_current_user(request: Request):
    return request.session.get("user")


def require_login(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user
