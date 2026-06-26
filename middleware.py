"""Application middleware — CSRF, session, security headers, audit log."""
import asyncio
import logging
import os
import re
import secrets
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

import database
import models

logger = logging.getLogger(__name__)

_SCRIPT_NONCE_RE = re.compile(rb"<script(?![^>]*\bnonce\b)", re.IGNORECASE)

_STATIC_MAX_AGE = 31_536_000  # 1 year in seconds


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection for POST requests.

    Accepts the token from either:
    - X-CSRFToken header  (AJAX / multipart fetch calls)
    - csrf_token field    (urlencoded HTML form body)

    Checking the header first means multipart upload routes never need
    to be exempted — their body is never read here.
    """

    _EXEMPT = ("/api/", "/login/", "/smr/confirm/")

    async def dispatch(self, request: Request, call_next):
        if os.getenv("TESTING") == "1":
            return await call_next(request)
        if request.method == "POST":
            path = request.url.path
            if not any(path.startswith(e) for e in self._EXEMPT):
                submitted = request.headers.get("X-CSRFToken")
                if not submitted:
                    ct = request.headers.get("content-type", "")
                    if "application/x-www-form-urlencoded" in ct or not ct:
                        try:
                            body      = await request.body()
                            params    = parse_qs(body.decode("utf-8"))
                            submitted = (params.get("csrf_token") or [None])[0]
                        except Exception:
                            submitted = None
                expected = request.session.get("csrf_token", "")
                if not (expected and submitted
                        and secrets.compare_digest(str(submitted), expected)):
                    logger.warning("CSRF check failed: path=%s ip=%s",
                                   path, request.client.host if request.client else "?")
                    return HTMLResponse(
                        "<h2>403 Forbidden</h2>"
                        "<p>Неверный CSRF-токен. "
                        "<a href='javascript:history.back()'>Назад</a></p>",
                        status_code=403,
                    )
        return await call_next(request)


class SessionVersionMiddleware(BaseHTTPMiddleware):
    """Invalidates the session when session_version has been bumped in the DB.

    Triggered by password resets so that old cookies are immediately rejected.
    """

    _SKIP = ("/login", "/static", "/api/ping")

    async def dispatch(self, request: Request, call_next):
        user = request.session.get("user")
        if user and not any(request.url.path.startswith(s) for s in self._SKIP):
            sv_cookie = user.get("sv", 1)
            try:
                with database.db_session() as db:
                    db_user = db.query(models.User).filter_by(id=user["id"]).first()
                    if db_user and (db_user.session_version or 1) != sv_cookie:
                        request.session.pop("user", None)
                        return RedirectResponse("/login", status_code=302)
            except Exception:
                pass
        return await call_next(request)


class AdminIPWhitelistMiddleware(BaseHTTPMiddleware):
    """Restricts /admin/* to a comma-separated IP allowlist (ADMIN_IP_WHITELIST env)."""

    _ADMIN_PREFIX = "/admin/"

    def __init__(self, app, whitelist: list[str]) -> None:
        super().__init__(app)
        self._ips = {ip.strip() for ip in whitelist if ip.strip()}

    async def dispatch(self, request: Request, call_next):
        if self._ips and request.url.path.startswith(self._ADMIN_PREFIX):
            user = request.session.get("user")
            if user and user.get("is_admin"):
                client_ip = (
                    request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                    or (request.client.host if request.client else "")
                )
                if client_ip not in self._ips:
                    logger.warning(
                        "Admin IP blocked: ip=%s path=%s user=%s",
                        client_ip, request.url.path, user.get("display_name"),
                    )
                    return HTMLResponse(
                        "<h2>403 Forbidden</h2>"
                        "<p>Ваш IP-адрес не разрешён для доступа к панели администратора.</p>"
                        "<p><a href='/'>На главную</a></p>",
                        status_code=403,
                    )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response and injects a CSP nonce into <script> tags."""

    _CSP = (
        "default-src 'self'; "
        "script-src 'self' 'nonce-{nonce}' cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
        "img-src 'self' data: blob: res.cloudinary.com *.cloudinary.com "
        "*.tile.openstreetmap.org *.basemaps.cartocdn.com; "
        "connect-src 'self' fcm.googleapis.com *.googleapis.com; "
        "font-src 'self' cdn.jsdelivr.net fonts.gstatic.com; "
        "frame-ancestors 'none'; "
        "object-src 'none';"
    )

    _BASE_HEADERS: dict[str, str] = {
        "X-Frame-Options":           "DENY",
        "X-Content-Type-Options":    "nosniff",
        "Referrer-Policy":           "strict-origin-when-cross-origin",
        "Permissions-Policy":        "geolocation=(), camera=(), microphone=()",
        "X-XSS-Protection":          "1; mode=block",
    }

    async def dispatch(self, request: Request, call_next):
        nonce                    = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response                 = await call_next(request)

        headers = dict(self._BASE_HEADERS)
        if os.getenv("RAILWAY_ENVIRONMENT"):
            headers["Strict-Transport-Security"] = f"max-age={_STATIC_MAX_AGE}; includeSubDomains"

        ct = response.headers.get("content-type", "")
        if "text/html" not in ct:
            if request.url.path.startswith("/static/"):
                response.headers["Cache-Control"] = (
                    f"public, max-age={_STATIC_MAX_AGE}, immutable"
                )
            for k, v in headers.items():
                response.headers[k] = v
            return response

        # HTML pages are user-specific — never cache
        headers["Cache-Control"]          = "no-store"
        headers["Content-Security-Policy"] = self._CSP.format(nonce=nonce)

        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        body    = b"".join(chunks)
        nonce_b = nonce.encode("ascii")
        body    = _SCRIPT_NONCE_RE.sub(b'<script nonce="' + nonce_b + b'"', body)

        new_resp = Response(content=body, status_code=response.status_code, media_type=ct)
        for k, v in response.headers.items():
            if k.lower() not in ("content-length", "content-type"):
                new_resp.headers[k] = v
        for k, v in headers.items():
            new_resp.headers[k] = v
        return new_resp


class AuditMiddleware(BaseHTTPMiddleware):
    """Asynchronously records page visits by authenticated users."""

    _SKIP_PREFIX = ("/static", "/api/ping", "/api/online", "/favicon", "/admin/audit")
    _SKIP_EXT    = (".css", ".js", ".png", ".ico", ".jpg", ".woff2", ".svg", ".webp")

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            if request.method != "GET":
                return response
            path = request.url.path
            if (any(path.startswith(s) for s in self._SKIP_PREFIX)
                    or any(path.endswith(e) for e in self._SKIP_EXT)):
                return response
            user = request.session.get("user")
            if not user:
                return response

            user_name  = user.get("display_name", "")
            user_phone = user.get("phone", "")
            ip         = request.client.host if request.client else ""

            def _write() -> None:
                db = database.SessionLocal()
                try:
                    db.add(models.AuditLog(
                        user_name=user_name, user_phone=user_phone, path=path, ip=ip,
                    ))
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()

            asyncio.get_running_loop().run_in_executor(None, _write)
        except Exception:
            pass
        return response
