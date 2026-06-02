"""
Загрузка файлов/фото.
Если заданы CLOUDINARY_* переменные — использует Cloudinary.
Иначе — сохраняет локально в static/uploads/ (работает, но на Railway сбрасывается при рестарте).
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CLOUD_NAME   = os.getenv("CLOUDINARY_CLOUD_NAME", "")
_API_KEY      = os.getenv("CLOUDINARY_API_KEY", "")
_API_SECRET   = os.getenv("CLOUDINARY_API_SECRET", "")
_USE_CLOUD    = bool(_CLOUD_NAME and _API_KEY and _API_SECRET)

if _USE_CLOUD:
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=_CLOUD_NAME,
        api_key=_API_KEY,
        api_secret=_API_SECRET,
        secure=True,
    )
    logger.info("cloud_storage: Cloudinary включён (cloud=%s)", _CLOUD_NAME)
else:
    logger.warning("cloud_storage: Cloudinary не настроен — фото сохраняются локально (эфемерное хранилище)")


def upload_photo(content: bytes, folder: str, filename: str) -> str:
    """
    Загружает фото. Возвращает:
    - полный https:// URL  (Cloudinary)
    - относительный путь uploads/folder/file (локально, для /static/)
    """
    if _USE_CLOUD:
        try:
            result = cloudinary.uploader.upload(
                content,
                folder=f"lenta/{folder}",
                resource_type="image",
                quality="auto",
                fetch_format="auto",
                overwrite=True,
            )
            return result["secure_url"]
        except Exception as e:
            logger.error("cloud_storage upload error: %s — fallback to local", e)

    # Локальный fallback
    save_dir = Path(f"static/uploads/{folder}")
    save_dir.mkdir(parents=True, exist_ok=True)
    (save_dir / filename).write_bytes(content)
    return f"uploads/{folder}/{filename}"


def upload_file(content: bytes, folder: str, filename: str,
                original_name: str = "") -> str:
    """
    Загружает произвольный файл (PDF, Word, Excel).
    Cloudinary поддерживает raw-ресурсы.
    Возвращает URL или относительный путь.
    """
    if _USE_CLOUD:
        try:
            result = cloudinary.uploader.upload(
                content,
                folder=f"lenta/{folder}",
                resource_type="raw",
                public_id=filename,
                overwrite=True,
                use_filename=True,
            )
            return result["secure_url"]
        except Exception as e:
            logger.error("cloud_storage upload_file error: %s — fallback to local", e)

    save_dir = Path(f"static/uploads/{folder}")
    save_dir.mkdir(parents=True, exist_ok=True)
    (save_dir / filename).write_bytes(content)
    return f"uploads/{folder}/{filename}"


def delete_photo(path_or_url: str, folder: str = ""):
    """Удаляет фото из Cloudinary или локально. Не бросает исключений."""
    if not path_or_url:
        return
    if _USE_CLOUD and path_or_url.startswith("http"):
        try:
            # Извлекаем public_id из URL Cloudinary
            # URL вида: https://res.cloudinary.com/<cloud>/image/upload/v123/lenta/folder/name.jpg
            parts = path_or_url.split("/upload/")
            if len(parts) == 2:
                public_id = parts[1].split("/", 1)[-1]  # убираем версию v123
                public_id = public_id.rsplit(".", 1)[0]  # убираем расширение
                cloudinary.uploader.destroy(f"lenta/{public_id}" if not public_id.startswith("lenta/") else public_id)
        except Exception as e:
            logger.warning("cloud_storage delete error: %s", e)
    else:
        # Локальный файл
        try:
            local = Path(f"static/{path_or_url}")
            if local.exists():
                local.unlink()
        except Exception:
            pass


def media_url(path: str) -> str:
    """Конвертирует путь в URL для использования в шаблонах и API."""
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return f"/static/{path}"
