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

        for attempt in range(2):
            try:
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
                elif resp.status_code >= 500 and attempt == 0:
                    continue
                else:
                    logger.error("Brevo API ошибка %s: %s", resp.status_code, resp.text)
                    return False
            except httpx.TimeoutException:
                if attempt == 0:
                    continue
                logger.error("Timeout при отправке email на %s", to)
                return False
        return False
    except Exception as e:
        logger.error("Ошибка отправки email на %s: %s", to, e, exc_info=True)
        return False


# ─── Шаблоны писем ───────────────────────────────────────────────────────────

def _raccoon_b64() -> str:
    """Возвращает base64 енота (80px) для вставки в письмо."""
    try:
        from PIL import Image
        img = Image.open(Path(__file__).parent.parent / "static" / "img" / "raccoon.png")
        img = img.convert("RGBA")
        img.thumbnail((80, 80), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""

_RACCOON_B64 = ""  # ленивая инициализация при первом вызове


def _base_template(content: str, title: str = "") -> str:
    global _RACCOON_B64
    if not _RACCOON_B64:
        _RACCOON_B64 = _raccoon_b64()

    raccoon_img = (
        f'<img src="data:image/png;base64,{_RACCOON_B64}" '
        f'width="56" height="56" style="border-radius:10px;display:block" alt="🦝">'
        if _RACCOON_B64 else
        '<span style="font-size:40px;line-height:1">🦝</span>'
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#e8f5e9;font-family:'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#e8f5e9" style="background:#e8f5e9;padding:24px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

  <!-- HEADER — bgcolor для поддержки всех почтовых клиентов -->
  <tr><td bgcolor="#1A5C22" style="background:#1A5C22;border-radius:16px 16px 0 0;padding:0">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td bgcolor="#1A5C22" style="background:#1A5C22;padding:22px 28px 0 28px">
          <table cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding-right:16px;vertical-align:middle">{raccoon_img}</td>
              <td style="vertical-align:middle">
                <div style="color:#FFD200;font-size:30px;font-weight:900;
                            letter-spacing:6px;line-height:1">ЛЕНТА</div>
                <div style="color:#a3d9a5;font-size:10px;
                            letter-spacing:2.5px;text-transform:uppercase;
                            margin-top:4px">Система управления проектами</div>
              </td>
              <td style="padding-left:14px;vertical-align:middle">
                <span style="background:#2A8436;color:#4ade80;
                             font-size:13px;font-weight:700;padding:4px 12px;
                             border-radius:20px;letter-spacing:1px;
                             border:1px solid #3CB34A">.PM</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <!-- Жёлтая полоса — фирменный элемент -->
      <tr>
        <td bgcolor="#1A5C22" style="background:#1A5C22;padding:16px 28px 0 28px">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td bgcolor="#FFD200" style="background:#FFD200;height:3px;font-size:0;line-height:0">&nbsp;</td></tr>
          </table>
        </td>
      </tr>
      {f'<tr><td bgcolor="#1A5C22" style="background:#1A5C22;padding:12px 28px 20px;color:#e8f5e9;font-size:13px;font-weight:600;letter-spacing:.5px">{title}</td></tr>' if title else '<tr><td bgcolor="#1A5C22" style="background:#1A5C22;padding:8px 0"></td></tr>'}
    </table>
  </td></tr>

  <!-- CONTENT -->
  <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:32px 32px 28px;
                 border-left:3px solid #3CB34A;border-right:1px solid #e8f5e9">
    {content}
  </td></tr>

  <!-- FOOTER -->
  <tr><td bgcolor="#1A5C22" style="background:#1A5C22;border-radius:0 0 16px 16px;padding:14px 28px">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="color:#a3d9a5;font-size:11px;vertical-align:middle">
          Лента.PM · Система управления проектами
        </td>
        <td align="right" style="vertical-align:middle">
          <span style="font-size:22px">🦝</span>
        </td>
      </tr>
    </table>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


def notify_task_assigned(to_email: str, assignee_name: str,
                          task_title: str, creator: str,
                          deadline_str: str, project_name: str) -> bool:
    deadline_line = f"<p><b>Дедлайн:</b> {deadline_str}</p>" if deadline_str else ""
    project_line  = f"<p><b>Проект:</b> {project_name}</p>" if project_name else ""
    content = f"""
        <h2 style="color:#1a2e1c">Вам поставлена новая задача</h2>
        <p style="font-size:16px;margin-bottom:4px">Добрый день.</p>
        <p><b>{creator}</b> поставил вам задачу:</p>
        <div style="background:#f4faf5;border-left:4px solid #3CB34A;
                    padding:12px 16px;margin:16px 0;border-radius:0 8px 8px 0">
          <b style="font-size:16px">{task_title}</b>
        </div>
        {project_line}{deadline_line}
        <p>Откройте систему чтобы посмотреть детали.</p>
    """
    return send_email(to_email, f"Новая задача: {task_title}",
                      _base_template(content, title="📋 Новая задача"))


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
        <p style="font-size:16px;margin-bottom:4px">Добрый день.</p>
        <p>По задаче <b>«{task_title}»</b>:</p>
        <div style="text-align:center;margin:20px 0">
          <span style="background:{color};color:#fff;padding:8px 20px;
                       border-radius:20px;font-weight:700">{new_status}</span>
        </div>
        <p style="color:#666">Исполнитель: {assignee_name}</p>
        {comment_block}
    """
    return send_email(to_email, f"Задача «{task_title}» — {new_status}",
                      _base_template(content, title=f"🔄 Статус задачи: {new_status}"))


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
                f'<span style="color:#dc2626;font-size:18px;font-weight:900">✗</span> '
                f'<b style="color:#dc2626;font-size:14px">{item["name"]}</b>'
                f'{comment_html}{photo_note}</div>'
            )
        failed_block = f"""
        <div style="margin-top:16px">
          <b style="color:#dc2626">Не выполнено ({len(failed_items)}):</b>
          <div style="background:#fff5f5;border:1px solid #fecaca;
                      border-radius:8px;padding:8px 12px;margin-top:8px">{rows}</div>
        </div>"""

    not_done = total - done
    content = f"""
        <p style="font-size:16px;margin-bottom:4px">Добрый день.</p>
        <p style="margin-top:4px"><b>{submitted_by}</b> отправил отчёт ВПК{vpk_type}</p>
        <div style="background:#f4faf5;border-left:4px solid #3CB34A;
                    padding:12px 16px;margin:16px 0;border-radius:0 8px 8px 0">
          <b style="font-size:18px">ТК {tk_number}</b>
          {"<br><span style='color:#666;font-size:13px'>" + project_name + "</span>" if project_name else ""}
        </div>
        <p style="font-size:15px">Выполнено: <b>{done}/{total}</b></p>
        <p style="font-size:15px;color:#dc2626">Не выполнено: <b>{not_done}</b></p>
        {failed_block}
        <p style="color:#999;font-size:12px;margin-top:16px">Отправлено: {submitted_at}</p>
    """
    return send_email(
        to_email,
        f"ВПК{vpk_type} — ТК {tk_number}: {done}/{total}, нарушений {not_done}",
        _base_template(content, title=f"📋 Отчёт ВПК{vpk_type} · ТК {tk_number}"),
        attachments=attachments or None,
    )


def notify_task_completed(to_email: str, creator_name: str,
                          task_title: str, assignee_name: str,
                          comment: str = "", photo_paths: list | None = None,
                          project_name: str = "") -> bool:
    """Отчёт о выполнении задачи — уходит постановщику при закрытии."""
    project_line = f"<p><b>Проект:</b> {project_name}</p>" if project_name else ""
    comment_block = (
        f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;'
        f'padding:14px;border-radius:8px;margin:16px 0">'
        f'<b style="color:#15803d">Комментарий исполнителя:</b>'
        f'<div style="margin-top:8px;white-space:pre-wrap;color:#1a1a1a">{comment}</div></div>'
        if comment else ""
    )
    attachments = []
    photo_block = ""
    if photo_paths:
        photo_items = ""
        for idx, rel_path in enumerate(photo_paths, 1):
            full = Path("static") / rel_path
            if not full.exists():
                continue
            ext  = full.suffix or ".jpg"
            name = f"фото_{idx}{ext}"
            attachments.append({"name": name, "path": str(full)})
            photo_items += (
                f'<div style="color:#2563eb;font-size:13px;padding:4px 0">'
                f'📎 {name}</div>'
            )
        if photo_items:
            photo_block = (
                f'<div style="background:#eff6ff;border:1px solid #bfdbfe;'
                f'border-radius:8px;padding:12px;margin-top:12px">'
                f'<b style="color:#1d4ed8">Фотоотчёт ({len(attachments)} фото):</b>'
                f'{photo_items}</div>'
            )
    content = f"""
        <h2 style="color:#15803d">✅ Задача выполнена</h2>
        <p style="font-size:16px;margin-bottom:4px">Добрый день.</p>
        <p>Исполнитель <b>{assignee_name}</b> завершил задачу:</p>
        <div style="background:#f4faf5;border-left:4px solid #3CB34A;
                    padding:12px 16px;margin:16px 0;border-radius:0 8px 8px 0">
          <b style="font-size:16px">{task_title}</b>
        </div>
        {project_line}{comment_block}{photo_block}
    """
    return send_email(
        to_email,
        f"✅ Задача выполнена: {task_title}",
        _base_template(content, title="✅ Задача выполнена"),
        attachments=attachments or None,
    )


def send_smr_task_done(to_email: str, task_name: str, project_name: str,
                       tk_number: str, plan_date: str, completed_by: str) -> bool:
    """Отчёт о выполнении этапа графика СМР."""
    content = f"""
        <h2 style="color:#15803d">Этап выполнен — График СМР</h2>
        <p style="font-size:16px">Добрый день.</p>
        <p>Этап работ отмечен как выполненный:</p>
        <div style="background:#f0fdf4;border-left:4px solid #16a34a;
                    padding:14px 18px;margin:16px 0;border-radius:0 8px 8px 0">
          <b style="font-size:16px">✅ {task_name}</b><br>
          <span style="color:#666;font-size:13px">ТК {tk_number} · {project_name}</span><br>
          <span style="color:#666;font-size:13px">Плановая дата: <b>{plan_date}</b></span>
        </div>
        <p style="color:#555;font-size:14px">Отметил: <b>{completed_by}</b></p>
    """
    return send_email(
        to_email,
        f"✅ Выполнено: {task_name} — ТК {tk_number}",
        _base_template(content, title="✅ График СМР · Этап выполнен"),
    )


def send_smr_confirmation(to_email: str, task_name: str, project_name: str,
                          tk_number: str, plan_date: str,
                          confirm_url: str, reject_url: str) -> bool:
    """Письмо с кнопками Подтвердить / Отклонить для вехи графика СМР."""
    content = f"""
        <h2 style="color:#1a2e1c">Подтверждение вехи — График СМР</h2>
        <p style="font-size:16px">Добрый день.</p>
        <p>Вас просят подтвердить выполнение этапа:</p>
        <div style="background:#f4faf5;border-left:4px solid #3CB34A;
                    padding:14px 18px;margin:16px 0;border-radius:0 8px 8px 0">
          <b style="font-size:16px">{task_name}</b><br>
          <span style="color:#666;font-size:13px">ТК {tk_number} · {project_name}</span><br>
          <span style="color:#666;font-size:13px">Плановая дата: <b>{plan_date}</b></span>
        </div>
        <table cellpadding="0" cellspacing="0" style="margin:24px auto">
          <tr>
            <td style="padding-right:12px">
              <a href="{confirm_url}"
                 style="display:inline-block;background:#16a34a;color:#fff;
                        font-weight:700;font-size:15px;padding:14px 32px;
                        border-radius:50px;text-decoration:none">
                ✅ Подтвердить
              </a>
            </td>
            <td>
              <a href="{reject_url}"
                 style="display:inline-block;background:#dc2626;color:#fff;
                        font-weight:700;font-size:15px;padding:14px 32px;
                        border-radius:50px;text-decoration:none">
                ❌ Отклонить
              </a>
            </td>
          </tr>
        </table>
        <p style="color:#999;font-size:12px;text-align:center">
          Если нажать кнопку несколько раз — ошибки не будет, учитывается первый ответ.
        </p>
    """
    return send_email(
        to_email,
        f"Подтверждение: {task_name} — ТК {tk_number}",
        _base_template(content, title="📋 График СМР · Подтверждение вехи"),
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
        <p style="font-size:16px;margin-bottom:4px">Добрый день.</p>
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
