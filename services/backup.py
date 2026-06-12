"""Автоматический pg_dump бэкап. Запускается APScheduler-ом каждую ночь в 03:00."""
import asyncio
import glob
import logging
import os
import pathlib
import subprocess
from datetime import date

logger = logging.getLogger(__name__)

BACKUP_DIR  = os.getenv("BACKUP_DIR", "/tmp/lenta_backups")
KEEP_DAYS   = int(os.getenv("BACKUP_KEEP_DAYS", "7"))


def _do_backup() -> str:
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or "postgresql" not in db_url:
        return "skip: not postgresql"

    pathlib.Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    fname = f"{BACKUP_DIR}/lenta_{date.today().isoformat()}.sql"

    result = subprocess.run(
        ["pg_dump", "--no-password", "--format=plain", db_url],
        capture_output=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode()[:400])

    pathlib.Path(fname).write_bytes(result.stdout)

    # Удаляем старые бэкапы сверх KEEP_DAYS
    all_backups = sorted(glob.glob(f"{BACKUP_DIR}/lenta_*.sql"))
    for old in all_backups[:-KEEP_DAYS]:
        pathlib.Path(old).unlink(missing_ok=True)

    return f"{fname} ({len(result.stdout):,} bytes)"


async def run_pg_backup():
    """Точка входа для APScheduler — запускает pg_dump в отдельном потоке."""
    try:
        result = await asyncio.to_thread(_do_backup)
        logger.info("auto-backup OK: %s", result)
    except FileNotFoundError:
        logger.warning("auto-backup: pg_dump не найден на сервере")
    except Exception as e:
        logger.error("auto-backup failed: %s", e)
