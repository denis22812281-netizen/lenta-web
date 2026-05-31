"""
Email-уведомления через Brevo HTTP API (порт 443, не блокируется Railway).
Активируется если задана BREVO_API_KEY.
"""
import io
import os
import base64
import logging
from pathlib import Path
import httpx

try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
APP_URL       = os.getenv("APP_URL", "").rstrip("/")

_SENDER_EMAIL = "lenta.pm@mail.ru"
_SENDER_NAME  = "Лента.PM"
_API_URL      = "https://api.brevo.com/v3/smtp/email"

EMAIL_ENABLED = bool(BREVO_API_KEY)
logger.warning("Email init: enabled=%s sender=%s", EMAIL_ENABLED, _SENDER_EMAIL)


def _compress_photo(path: Path, max_px: int = 1200, quality: int = 70) -> bytes:
    """Сжимает фото до max_px и quality%. Без Pillow — возвращает оригинал."""
    if not _PIL_AVAILABLE:
        return path.read_bytes()
    try:
        with _PILImage.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_px, max_px), _PILImage.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue()
    except Exception:
        return path.read_bytes()


def send_email(to: str, subject: str, body_html: str,
               attachments: list | None = None) -> bool:
    """attachments: список {"name": "file.jpg", "path": "/abs/path/to/file"}"""
    if not EMAIL_ENABLED:
        logger.warning("Email отключён — BREVO_API_KEY не задан, пропуск: %s", to)
        return False
    if not to or "@" not in to:
        logger.warning("Email: некорректный адрес: %r", to)
        return False
    try:
        payload: dict = {
            "sender":      {"name": _SENDER_NAME, "email": _SENDER_EMAIL},
            "to":          [{"email": to}],
            "subject":     subject,
            "htmlContent": body_html,
        }
        if attachments:
            encoded = []
            for att in attachments:
                p = Path(att["path"])
                if not p.exists():
                    continue
                raw = _compress_photo(p)
                encoded.append({
                    "name":    att["name"],
                    "content": base64.b64encode(raw).decode(),
                })
            if encoded:
                payload["attachment"] = encoded

        resp = httpx.post(
            _API_URL,
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        if resp.status_code in (200, 201):
            logger.warning("Email отправлен: [%s] → %s (вложений: %d)",
                           subject, to, len(payload.get("attachment", [])))
            return True
        else:
            logger.error("Brevo API ошибка %s: %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Ошибка отправки email на %s: %s", to, e, exc_info=True)
        return False


# ─── Шаблоны писем ───────────────────────────────────────────────────────────

def _base_template(content: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#0D2010;padding:16px 24px;border-radius:8px 8px 0 0">
        <span style="color:#FFD200;font-size:22px;font-weight:900;letter-spacing:4px">ЛЕНТА</span>
        <span style="color:#4ade80;font-size:13px;margin-left:8px">.PM</span>
      </div>
      <div style="background:#fff;padding:24px;border:1px solid #e8f5e9;border-top:none;border-radius:0 0 8px 8px">
        {content}
      </div>
      <div style="text-align:center;color:#aaa;font-size:11px;padding:12px">
        Лента.PM — Система управления проектами
      </div>
    </div>
    """


def notify_task_assigned(to_email: str, assignee_name: str,
                          task_title: str, creator: str,
                          deadline_str: str, project_name: str) -> bool:
    deadline_line = f"<p><b>Дедлайн:</b> {deadline_str}</p>" if deadline_str else ""
    project_line  = f"<p><b>Проект:</b> {project_name}</p>" if project_name else ""
    content = f"""
        <h2 style="color:#1a2e1c">Вам поставлена новая задача</h2>
        <p>Привет, <b>{assignee_name}</b>!</p>
        <p><b>{creator}</b> поставил вам задачу:</p>
        <div style="background:#f4faf5;border-left:4px solid #3CB34A;
                    padding:12px 16px;margin:16px 0;border-radius:0 8px 8px 0">
          <b style="font-size:16px">{task_title}</b>
        </div>
        {project_line}{deadline_line}
        <p>Откройте систему чтобы посмотреть детали.</p>
    """
    return send_email(to_email, f"Новая задача: {task_title}", _base_template(content))


def notify_task_status_changed(to_email: str, creator_name: str,
                                task_title: str, new_status: str,
                                assignee_name: str, comment: str = "") -> bool:
    status_colors = {"В работе": "#2563eb", "На проверке": "#d97706", "Завершена": "#16a34a"}
    color = status_colors.get(new_status, "#6b7280")
    comment_block = (
        f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;'
        f'padding:12px;border-radius:8px;margin-top:12px">'
        f'<b>Комментарий:</b><br>{comment}</div>'
        if comment else ""
    )
    content = f"""
        <h2 style="color:#1a2e1c">Статус задачи изменён</h2>
        <p>Привет, <b>{creator_name}</b>!</p>
        <p>По задаче <b>«{task_title}»</b>:</p>
        <div style="text-align:center;margin:20px 0">
          <span style="background:{color};color:#fff;padding:8px 20px;
                       border-radius:20px;font-weight:700">{new_status}</span>
        </div>
        <p style="color:#666">Исполнитель: {assignee_name}</p>
        {comment_block}
    """
    return send_email(to_email, f"Задача «{task_title}» — {new_status}", _base_template(content))


def notify_vpk_report(to_email: str, recipient_name: str,
                      vpk_type: int, tk_number: str, project_name: str,
                      submitted_by: str, done: int, total: int,
                      submitted_at: str, failed_items: list | None = None) -> bool:
    pct   = int(done / total * 100) if total else 0
    color = "#16a34a" if pct >= 80 else "#d97706" if pct >= 50 else "#dc2626"

    attachments = []
    failed_block = ""
    if failed_items:
        rows = ""
        for idx, item in enumerate(failed_items, 1):
            photo_note = ""
            if item.get("photo_path"):
                full_path = Path("static") / item["photo_path"]
                if full_path.exists():
                    ext  = full_path.suffix or ".jpg"
                    name = f"фото_{idx}{ext}"
                    attachments.append({"name": name, "path": str(full_path)})
                    photo_note = (
                        f'<div style="color:#2563eb;font-size:12px;margin-top:4px">'
                        f'📎 Фото прилагается: {name}</div>'
                    )
            comment_html = (
                f'<div style="color:#555;font-size:12px;margin-top:4px">{item["comment"]}</div>'
                if item.get("comment") else ""
            )
            rows += (
                f'<div style="padding:10px 0;border-bottom:1px solid #fee2e2">'
                f'<span style="color:#dc2626">✗</span> {item["name"]}'
                f'{comment_html}{photo_note}</div>'
            )
        failed_block = f"""
        <div style="margin-top:16px">
          <b style="color:#dc2626">Не выполнено ({len(failed_items)}):</b>
          <div style="background:#fff5f5;border:1px solid #fecaca;
                      border-radius:8px;padding:8px 12px;margin-top:8px">{rows}</div>
        </div>"""

    content = f"""
        <h2 style="color:#1a2e1c">Новый отчёт ВПК{vpk_type}</h2>
        <p>Привет, <b>{recipient_name}</b>!</p>
        <p><b>{submitted_by}</b> отправил отчёт:</p>
        <div style="background:#f4faf5;border-left:4px solid #3CB34A;
                    padding:12px 16px;margin:16px 0;border-radius:0 8px 8px 0">
          <b style="font-size:18px">ТК {tk_number}</b>
          {"<br><span style='color:#666;font-size:13px'>" + project_name + "</span>" if project_name else ""}
        </div>
        <p>Выполнено:
          <span style="background:{color};color:#fff;padding:4px 14px;
                       border-radius:12px;font-weight:700">{done} / {total} ({pct}%)</span>
        </p>
        {failed_block}
        <p style="color:#999;font-size:12px;margin-top:16px">Отправлено: {submitted_at}</p>
    """
    return send_email(
        to_email,
        f"ВПК{vpk_type} — ТК {tk_number}: {done}/{total}, нарушений {total - done}",
        _base_template(content),
        attachments=attachments or None,
    )


def notify_deadline_tomorrow(to_email: str, manager_name: str, projects: list) -> bool:
    if not projects:
        return False
    rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #e8f5e9'>{p['tk']}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #e8f5e9'>{p['name']}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #e8f5e9;color:#dc2626'>"
        f"<b>{p['deadline']}</b></td></tr>"
        for p in projects
    )
    content = f"""
        <h2 style="color:#dc2626">Дедлайны завтра</h2>
        <p>Привет, <b>{manager_name}</b>!</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0">
          <thead><tr style="background:#f4faf5">
            <th style="padding:8px;text-align:left">ТК</th>
            <th style="padding:8px;text-align:left">Название</th>
            <th style="padding:8px;text-align:left">Дедлайн</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
    """
    return send_email(to_email, f"Дедлайны завтра ({len(projects)} проектов)", _base_template(content))
