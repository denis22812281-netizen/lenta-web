"""
Email-уведомления через корпоративный SMTP.
Активируется если заданы переменные SMTP_HOST, SMTP_USER, SMTP_PASSWORD.
Если не заданы — молча пропускает (система работает без email).
"""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

SMTP_HOST     = os.getenv("SMTP_HOST", "")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", SMTP_USER)

EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_email(to: str, subject: str, body_html: str) -> bool:
    """Отправить письмо. Возвращает True при успехе, False при ошибке."""
    if not EMAIL_ENABLED:
        logger.debug("Email отключён (SMTP_HOST не задан), пропускаем отправку на %s", to)
        return False
    if not to or "@" not in to:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM
        msg["To"]      = to
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to], msg.as_string())

        logger.info("Email отправлен: %s → %s", subject, to)
        return True
    except Exception as e:
        logger.warning("Ошибка отправки email на %s: %s", to, e)
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
        {project_line}
        {deadline_line}
        <p>Откройте систему чтобы посмотреть детали и взять задачу в работу.</p>
    """
    return send_email(to_email, f"Новая задача: {task_title}", _base_template(content))


def notify_task_status_changed(to_email: str, creator_name: str,
                                task_title: str, new_status: str,
                                assignee_name: str,
                                comment: str = "") -> bool:
    status_colors = {
        "В работе":    "#2563eb",
        "На проверке": "#d97706",
        "Завершена":   "#16a34a",
    }
    color   = status_colors.get(new_status, "#6b7280")
    comment_block = (
        f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;'
        f'padding:12px;border-radius:8px;margin-top:12px">'
        f'<b>Комментарий исполнителя:</b><br>{comment}</div>'
        if comment else ""
    )
    content = f"""
        <h2 style="color:#1a2e1c">Статус задачи изменён</h2>
        <p>Привет, <b>{creator_name}</b>!</p>
        <p>По задаче <b>«{task_title}»</b> изменился статус:</p>
        <div style="text-align:center;margin:20px 0">
          <span style="background:{color};color:#fff;padding:8px 20px;
                       border-radius:20px;font-weight:700;font-size:15px">
            {new_status}
          </span>
        </div>
        <p style="color:#666">Исполнитель: {assignee_name}</p>
        {comment_block}
    """
    return send_email(
        to_email,
        f"Задача «{task_title}» — {new_status}",
        _base_template(content)
    )


def notify_deadline_tomorrow(to_email: str, manager_name: str,
                              projects: list) -> bool:
    """Список проектов с дедлайном завтра."""
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
        <p>Завтра истекает срок по следующим проектам:</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0">
          <thead>
            <tr style="background:#f4faf5">
              <th style="padding:8px;text-align:left">ТК</th>
              <th style="padding:8px;text-align:left">Название</th>
              <th style="padding:8px;text-align:left">Дедлайн</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
    """
    return send_email(
        to_email,
        f"Дедлайны завтра ({len(projects)} проектов)",
        _base_template(content)
    )
