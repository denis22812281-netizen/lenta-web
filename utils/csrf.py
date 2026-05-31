import secrets
from fastapi import Request


def get_csrf_token(request: Request) -> str:
    """Возвращает CSRF-токен из сессии, генерирует если нет."""
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(32)
    return request.session["csrf_token"]
