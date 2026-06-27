"""Data → Excel conversion tool (admin only): photo, text, multi-photo, compare, merge."""
import asyncio
import io
import logging
import re
import time as _time
import urllib.parse
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import require_admin, templates
from services.tools_service import (
    _PROMPTS,
    _TEXT_PROMPTS,
    _TYPE_RU,
    BUILDERS,
    build_comparison,
    build_table,
    call_ai,
    call_text_ai,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory templates (per user, persistent until server restart) ────────────
_TEMPLATES: dict[int, list[dict]] = {}
_TEMPLATES_MAX = 20


def _template_save(user_id: int, name: str, output_type: str, mode: str) -> str:
    uid = str(uuid.uuid4())[:8]
    items = _TEMPLATES.get(user_id, [])
    items = [i for i in items if i["name"] != name]
    items.append({"id": uid, "name": name, "output_type": output_type,
                  "mode": mode, "created_at": _time.strftime("%d.%m.%Y %H:%M")})
    _TEMPLATES[user_id] = items[-_TEMPLATES_MAX:]
    return uid


def _template_delete(user_id: int, template_id: str) -> bool:
    items = _TEMPLATES.get(user_id, [])
    before = len(items)
    _TEMPLATES[user_id] = [i for i in items if i["id"] != template_id]
    return len(_TEMPLATES[user_id]) < before


# ── In-memory history (per user, max 10 items, TTL 24h) ──────────────────────
_HISTORY: dict[int, list[dict]] = {}
_HISTORY_MAX = 10
_HISTORY_TTL = 86400


def _history_save(user_id: int, filename: str, out_type: str, blob: bytes) -> str:
    uid = str(uuid.uuid4())[:8]
    now = _time.time()
    items = [i for i in _HISTORY.get(user_id, []) if now - i["ts"] < _HISTORY_TTL]
    items.append({"id": uid, "ts": now, "filename": filename, "type": out_type,
                  "blob": blob, "size": len(blob)})
    _HISTORY[user_id] = items[-_HISTORY_MAX:]
    return uid


def _history_get(user_id: int, item_id: str) -> dict | None:
    now = _time.time()
    for item in _HISTORY.get(user_id, []):
        if item["id"] == item_id and now - item["ts"] < _HISTORY_TTL:
            return item
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/tools/photo-to-excel", response_class=HTMLResponse)
async def photo_to_excel_page(request: Request, user: dict = Depends(require_admin)):
    return templates.TemplateResponse("photo_to_excel.html", {
        "request": request, "user": user,
    })


@router.post("/api/tools/photo-to-excel")
async def photo_to_excel_api(
    request:     Request,
    user:        dict       = Depends(require_admin),
    photo:       UploadFile = File(...),
    output_type: str        = Form("table"),
):
    try:
        if output_type not in BUILDERS:
            output_type = "table"

        image_bytes  = await photo.read()
        content_type = photo.content_type or "image/jpeg"
        if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            content_type = "image/jpeg"

        data = await call_ai(image_bytes, content_type, output_type)
        wb   = BUILDERS[output_type](data)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        raw_title   = data.get("title", "data")
        ascii_title = re.sub(r"[^\w\- ]", "", raw_title, flags=re.ASCII)[:40].strip() or "data"
        filename    = f"{ascii_title}_{output_type}.xlsx"
        encoded     = urllib.parse.quote(f"{raw_title[:40]}_{_TYPE_RU[output_type]}.xlsx")
        disposition = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded}'

        blob = buf.getvalue()
        _history_save(user["id"], filename, output_type, blob)

        return StreamingResponse(
            io.BytesIO(blob),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": disposition},
        )
    except Exception as exc:
        logger.error("photo-to-excel error: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/tools/photo-to-excel/preview")
async def photo_to_excel_preview(
    request:     Request,
    user:        dict       = Depends(require_admin),
    photo:       UploadFile = File(...),
    output_type: str        = Form("auto"),
):
    """Return extracted JSON for frontend preview before downloading Excel."""
    try:
        image_bytes  = await photo.read()
        content_type = photo.content_type or "image/jpeg"
        if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            content_type = "image/jpeg"

        otype = output_type if output_type in _PROMPTS else "auto"
        data  = await call_ai(image_bytes, content_type, otype)

        if otype == "auto":
            detected = data.get("detected_type", "table")
            data["_resolved_type"] = detected
        else:
            data["_resolved_type"] = otype

        return JSONResponse({"ok": True, "data": data})
    except Exception as exc:
        logger.error("preview error: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/tools/text-to-excel")
async def text_to_excel_api(
    request:     Request,
    user:        dict = Depends(require_admin),
    text:        str  = Form(...),
    output_type: str  = Form("table"),
):
    """Convert pasted/typed text → Excel using text-only AI."""
    try:
        if not text.strip():
            return JSONResponse({"error": "Текст не может быть пустым"}, status_code=400)

        otype = output_type if output_type in _PROMPTS else "table"
        prompt = _TEXT_PROMPTS.get(otype, _TEXT_PROMPTS["table"])
        full_prompt = f"{prompt}\n\nТекст для анализа:\n{text.strip()[:8000]}"

        data = await call_text_ai(full_prompt)

        if otype == "auto":
            otype = data.get("detected_type", "table")
            if otype not in BUILDERS:
                otype = "table"

        wb  = BUILDERS.get(otype, build_table)(data)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        raw_title   = data.get("title", "data")
        ascii_title = re.sub(r"[^\w\- ]", "", raw_title, flags=re.ASCII)[:40].strip() or "data"
        filename    = f"{ascii_title}_{otype}.xlsx"
        encoded     = urllib.parse.quote(f"{raw_title[:40]}_{_TYPE_RU.get(otype, otype)}.xlsx")
        disposition = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded}'

        blob = buf.getvalue()
        _history_save(user["id"], filename, otype, blob)

        return StreamingResponse(
            io.BytesIO(blob),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": disposition},
        )
    except Exception as exc:
        logger.error("text-to-excel error: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/tools/multi-photo-excel")
async def multi_photo_excel_api(
    request:     Request,
    user:        dict             = Depends(require_admin),
    photos:      List[UploadFile] = File(...),
    output_type: str              = Form("table"),
):
    """Multiple photos → one Excel file, each photo becomes a separate sheet."""
    try:
        if not photos:
            return JSONResponse({"error": "Нет файлов"}, status_code=400)

        from openpyxl import Workbook as _WB
        otype = output_type if output_type in _PROMPTS else "table"
        wb_final = _WB()
        wb_final.remove(wb_final.active)

        tasks_list = []
        for photo in photos[:10]:
            image_bytes  = await photo.read()
            content_type = photo.content_type or "image/jpeg"
            if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                content_type = "image/jpeg"
            tasks_list.append(call_ai(image_bytes, content_type, otype))

        results = await asyncio.gather(*tasks_list, return_exceptions=True)

        for idx, (photo, result) in enumerate(zip(photos, results), 1):
            if isinstance(result, Exception):
                logger.warning("multi-photo sheet %d error: %s", idx, result)
                ws = wb_final.create_sheet(f"Лист {idx} (ошибка)")
                ws.cell(1, 1, f"Ошибка обработки: {result}")
                continue
            wb_sheet = BUILDERS.get(otype, build_table)(result)
            src_ws   = wb_sheet.active
            sheet_name = re.sub(r"[^\w\s]", "", photo.filename or f"Лист {idx}")[:30] or f"Лист {idx}"
            dst_ws = wb_final.create_sheet(sheet_name)
            for row in src_ws.iter_rows():
                for cell in row:
                    nc = dst_ws.cell(row=cell.row, column=cell.column, value=cell.value)
                    if cell.has_style:
                        nc.font      = cell.font.copy()
                        nc.fill      = cell.fill.copy()
                        nc.border    = cell.border.copy()
                        nc.alignment = cell.alignment.copy()

        if not wb_final.sheetnames:
            return JSONResponse({"error": "Не удалось обработать ни один файл"}, status_code=500)

        buf = io.BytesIO()
        wb_final.save(buf)
        buf.seek(0)

        blob = buf.getvalue()
        fname = f"multi_{len(photos)}_sheets_{otype}.xlsx"
        _history_save(user["id"], fname, otype, blob)

        return StreamingResponse(
            io.BytesIO(blob),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    except Exception as exc:
        logger.error("multi-photo error: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/tools/compare-excel")
async def compare_excel_api(
    request: Request,
    user:    dict       = Depends(require_admin),
    photo1:  UploadFile = File(...),
    photo2:  UploadFile = File(...),
):
    """Two photos → Excel with 3 sheets: Source1, Source2, Diff (color-coded)."""
    try:
        b1, b2 = await photo1.read(), await photo2.read()
        m1 = photo1.content_type or "image/jpeg"
        m2 = photo2.content_type or "image/jpeg"
        if m1 not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            m1 = "image/jpeg"
        if m2 not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            m2 = "image/jpeg"

        data1, data2 = await asyncio.gather(
            call_ai(b1, m1, "table"),
            call_ai(b2, m2, "table"),
        )
        wb  = build_comparison(data1, data2)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        blob  = buf.getvalue()
        fname = "сравнение.xlsx"
        _history_save(user["id"], fname, "compare", blob)

        return StreamingResponse(
            io.BytesIO(blob),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename*=UTF-8\'\'{urllib.parse.quote(fname)}'},
        )
    except Exception as exc:
        logger.error("compare error: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/tools/merge-excel")
async def merge_excel_api(
    request:     Request,
    user:        dict             = Depends(require_admin),
    photos:      List[UploadFile] = File(...),
):
    """Multiple photos → one merged table (AI deduplicates and unifies structure)."""
    try:
        import json as _json
        if not photos:
            return JSONResponse({"error": "Нет файлов"}, status_code=400)

        tasks = [call_ai(await p.read(), p.content_type or "image/jpeg", "table")
                 for p in photos[:5]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        tables  = [r for r in results if not isinstance(r, Exception)]

        if not tables:
            return JSONResponse({"error": "Не удалось обработать файлы"}, status_code=500)

        if len(tables) == 1:
            merged = tables[0]
        else:
            merge_prompt = (
                "У тебя есть несколько таблиц. Объедини их в одну, убери дублирующиеся строки, "
                "унифицируй заголовки. Верни ТОЛЬКО валидный JSON:\n"
                '{"title":"Объединённая таблица","headers":[...],"rows":[[...]]}\n\n'
                "Таблицы:\n" +
                "\n".join(f"Таблица {i+1}:\n{_json.dumps(t, ensure_ascii=False)}" for i, t in enumerate(tables))
            )
            merged = await call_text_ai(merge_prompt)

        wb  = build_table(merged)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        blob  = buf.getvalue()
        fname = "объединение.xlsx"
        _history_save(user["id"], fname, "merge", blob)

        return StreamingResponse(
            io.BytesIO(blob),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename*=UTF-8\'\'{urllib.parse.quote(fname)}'},
        )
    except Exception as exc:
        logger.error("merge error: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/tools/history")
async def conversion_history(request: Request, user: dict = Depends(require_admin)):
    """Return last N conversion history items for current user."""
    now = _time.time()
    items = [
        {"id": i["id"], "filename": i["filename"], "type": i["type"],
         "size": i["size"], "age_min": int((now - i["ts"]) / 60)}
        for i in _HISTORY.get(user["id"], [])
        if now - i["ts"] < _HISTORY_TTL
    ]
    return JSONResponse({"items": list(reversed(items))})


@router.get("/api/tools/history/{item_id}")
async def download_history_item(item_id: str, request: Request,
                                user: dict = Depends(require_admin)):
    """Re-download a previously converted file."""
    item = _history_get(user["id"], item_id)
    if not item:
        return JSONResponse({"error": "Файл не найден или истёк срок хранения"}, status_code=404)
    encoded = urllib.parse.quote(item["filename"])
    return StreamingResponse(
        io.BytesIO(item["blob"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{item["filename"]}"; filename*=UTF-8\'\'{encoded}'},
    )


# ── Templates (DB-backed, survive server restarts) ─────────────────────────────

@router.get("/api/tools/templates")
async def list_templates(request: Request, user: dict = Depends(require_admin),
                         db: Session = Depends(get_db)):
    rows = db.query(models.ConversionTemplate).filter(
        models.ConversionTemplate.user_id == user["id"]
    ).order_by(models.ConversionTemplate.created_at).all()
    return JSONResponse({"templates": [
        {"id": r.id, "name": r.name, "output_type": r.output_type, "mode": r.mode,
         "created_at": r.created_at.strftime("%d.%m.%Y %H:%M") if r.created_at else ""}
        for r in rows
    ]})


@router.post("/api/tools/templates")
async def save_template(request: Request, user: dict = Depends(require_admin),
                        db: Session = Depends(get_db)):
    data = await request.json()
    name = (data.get("name") or "").strip()[:60]
    if not name:
        return JSONResponse({"error": "Название обязательно"}, status_code=400)
    output_type = data.get("output_type", "auto")
    mode        = data.get("mode", "photo")
    if output_type not in _PROMPTS:
        output_type = "auto"

    uid = str(uuid.uuid4())[:8]
    existing = db.query(models.ConversionTemplate).filter(
        models.ConversionTemplate.user_id == user["id"],
        models.ConversionTemplate.name == name,
    ).first()
    if existing:
        existing.output_type = output_type
        existing.mode = mode
        uid = existing.id
    else:
        count = db.query(models.ConversionTemplate).filter(
            models.ConversionTemplate.user_id == user["id"]).count()
        if count >= 20:
            oldest = db.query(models.ConversionTemplate).filter(
                models.ConversionTemplate.user_id == user["id"]
            ).order_by(models.ConversionTemplate.created_at).first()
            if oldest:
                db.delete(oldest)
        db.add(models.ConversionTemplate(
            id=uid, user_id=user["id"], name=name,
            output_type=output_type, mode=mode,
        ))
    db.commit()
    return JSONResponse({"ok": True, "id": uid})


@router.delete("/api/tools/templates/{template_id}")
async def delete_template(template_id: str, request: Request,
                          user: dict = Depends(require_admin),
                          db: Session = Depends(get_db)):
    row = db.query(models.ConversionTemplate).filter(
        models.ConversionTemplate.id == template_id,
        models.ConversionTemplate.user_id == user["id"],
    ).first()
    if not row:
        return JSONResponse({"error": "Шаблон не найден"}, status_code=404)
    db.delete(row)
    db.commit()
    return JSONResponse({"ok": True})
