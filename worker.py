"""Standalone backup worker — запускается Railway как отдельный process.

Выполняет:
  - PostgreSQL backup каждую ночь в 03:00 МСК
  - Push-уведомления о дедлайнах каждый день в 09:00 МСК

Запуск: python worker.py
"""
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL or "postgresql" not in DATABASE_URL:
    log.warning("DATABASE_URL не настроен или не PostgreSQL — worker завершается.")
    raise SystemExit(0)


def run_backup():
    try:
        from services.backup import run_pg_backup
        log.info("Запуск backup...")
        run_pg_backup()
        log.info("Backup завершён успешно.")
    except Exception as e:
        log.error("Ошибка backup: %s", e, exc_info=True)


def run_deadline_push():
    try:
        import database
        from services.push_service import send_deadline_push
        db = next(database.get_db())
        try:
            send_deadline_push(db)
            log.info("Deadline push отправлен.")
        finally:
            db.close()
    except Exception as e:
        log.error("Ошибка deadline push: %s", e, exc_info=True)


def main():
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="Europe/Moscow")
    scheduler.add_job(run_backup,        "cron", hour=3,  minute=0, id="backup")
    scheduler.add_job(run_deadline_push, "cron", hour=9,  minute=0, id="deadlines")

    log.info("Worker запущен. Backup в 03:00, deadline push в 09:00 (МСК).")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Worker остановлен.")


if __name__ == "__main__":
    main()
