from fastapi import UploadFile

# Allowed extensions grouped by kind — add new ones here if needed
_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}
_DOC_EXTS = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".csv", ".txt", ".zip"}
ALLOWED_EXTS = _PHOTO_EXTS | _DOC_EXTS


def check_magic_bytes(content: bytes, filename: str) -> None:
    """Raise ValueError if the file's actual type doesn't match its extension.

    Prevents attackers from renaming e.g. script.php → photo.jpg.
    Only checks formats we accept — passes through anything filetype can't identify.
    """
    import filetype

    ext = ("." + filename.rsplit(".", 1)[-1]).lower() if "." in filename else ""

    kind = filetype.guess(content[:512])
    if kind is None:
        # filetype can't identify it (text files, some office docs) — pass through
        return

    detected_mime = kind.mime  # e.g. "image/jpeg"

    photo_mimes = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic"}

    if ext in _PHOTO_EXTS and detected_mime not in photo_mimes:
        raise ValueError(f"Файл «{filename}» не является изображением (обнаружен {detected_mime})")

    if ext in {".pdf"} and detected_mime != "application/pdf":
        raise ValueError(f"Файл «{filename}» не является PDF")

    if ext in {".xlsx", ".xls"} and detected_mime not in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/zip",  # xlsx is a zip internally
    ):
        raise ValueError(f"Файл «{filename}» не является Excel-файлом")


async def read_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Читает UploadFile чанками, прерывает если размер превышает max_bytes."""
    chunks = []
    total = 0
    while True:
        chunk = await file.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"Файл превышает допустимый размер ({max_bytes // (1024*1024)} МБ)")
        chunks.append(chunk)
    return b"".join(chunks)
