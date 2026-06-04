from fastapi import UploadFile


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
