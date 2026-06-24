"""Отправка Web Push-уведомлений через VAPID."""
import json
import logging
import os
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
_CLAIMS = {"sub": "mailto:denis.mesmer@lenta.com"}


def _vapid():
    from py_vapid import Vapid
    return Vapid.from_string(_PRIVATE_KEY)


def is_configured() -> bool:
    return bool(_PRIVATE_KEY)


def send_push(subscription, title: str, body: str, url: str = "/") -> bool | None:
    """Отправить push одному подписчику.
    Возвращает True (успех), False (ошибка), None (подписка устарела → удалить).
    """
    if not is_configured():
        return False
    try:
        from pywebpush import WebPushException, webpush
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth_key,
                },
            },
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=_vapid(),
            vapid_claims=_CLAIMS,
            ttl=86400,
        )
        return True
    except Exception as exc:
        try:
            from pywebpush import WebPushException
            if isinstance(exc, WebPushException) and exc.response is not None:
                if exc.response.status_code in (404, 410):
                    return None
        except ImportError:
            pass
        logger.warning("push_send error: %s", exc)
        return False


def notify_user(db, display_name: str, title: str, body: str, url: str = "/") -> int:
    """Отправить push всем подпискам пользователя. Возвращает кол-во успехов."""
    import models
    subs = db.query(models.PushSubscription).filter_by(user_name=display_name).all()
    sent = 0
    for sub in subs:
        result = send_push(sub, title, body, url)
        if result is True:
            sent += 1
        elif result is None:
            db.delete(sub)
    if any(s for s in subs):
        db.commit()
    return sent


def notify_all(db, title: str, body: str, url: str = "/") -> int:
    """Отправить push всем подписчикам системы."""
    import models
    subs = db.query(models.PushSubscription).all()
    sent = 0
    expired = []
    for sub in subs:
        result = send_push(sub, title, body, url)
        if result is True:
            sent += 1
        elif result is None:
            expired.append(sub)
    for sub in expired:
        db.delete(sub)
    if expired:
        db.commit()
    return sent


# ─── Дедлайн-уведомления ─────────────────────────────────────────────────────

def send_deadline_push(db) -> int:
    """Отправить push по проектам с дедлайном ≤ 3 дня.
    Вызывается из планировщика каждое утро.
    """
    if not is_configured():
        return 0

    import models
    today = date.today()
    projects = db.query(models.Project).filter(
        models.Project.status != "Завершён",
        models.Project.end_date != None,
        models.Project.end_date >= today,
        models.Project.end_date <= today + timedelta(days=3),
    ).all()

    total = 0
    for p in projects:
        days = (p.end_date - today).days
        mgr = p.manager
        tk = p.tk_number or str(p.id)

        if days == 0:
            day_label = "сегодня"
        elif days == 1:
            day_label = "завтра"
        else:
            day_label = f"через {days} дн."

        title = f"⚠️ Дедлайн {day_label}: ТК {tk}"
        body = f"{p.name} — {p.end_date.strftime('%d.%m.%Y')}"
        url = f"/projects/{p.id}"

        if mgr:
            total += notify_user(db, mgr.name, title, body, url)

    logger.info("deadline_push: отправлено %d уведомлений по %d проектам", total, len(projects))
    return total
