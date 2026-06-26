"""Photo → Excel conversion tool (admin only)."""
import asyncio
import base64
import io
import json
import logging
import os
import re
import urllib.parse
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from config import AI_CLAUDE_MODEL, AI_GEMINI_MODEL, AI_MAX_OUTPUT_TOKENS
from deps import require_admin, templates

logger = logging.getLogger(__name__)
router = APIRouter()

_GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{AI_GEMINI_MODEL}:generateContent"
)

_COL_MIN_WIDTH = 12
_COL_MAX_WIDTH = 40
_COL_PADDING   = 4

_PROMPTS: dict[str, str] = {
    "table": (
        "Ты эксперт по извлечению данных из изображений. "
        "Посмотри на изображение и извлеки ВСЕ данные таблицы. "
        "Правила: "
        "1) title — реальное название таблицы с изображения (если нет — придумай по содержимому). "
        "2) headers — только названия столбцов (не строка данных). "
        "3) rows — все строки данных начиная с первой, НЕ включая заголовок. "
        "4) Если в таблице есть столбец с порядковыми номерами — включи его как есть, НЕ дублируй. "
        "Верни ТОЛЬКО валидный JSON без пояснений:\n"
        '{"title":"Реальное название","headers":["№","Столбец1","Столбец2"],'
        '"rows":[["1","значение1","значение2"],["2","значение3","значение4"]]}'
    ),
    "chart": (
        "Ты эксперт по извлечению данных из изображений. "
        "Посмотри на изображение и извлеки данные для построения графика. "
        "Если видишь данные с временным рядом — используй line, иначе bar. "
        "Верни ТОЛЬКО валидный JSON без пояснений:\n"
        '{"title":"Название","chart_type":"bar",'
        '"categories":["янв","фев","мар"],'
        '"series":[{"name":"Серия 1","values":[10,20,30]}]}'
    ),
    "diagram": (
        "Ты эксперт по извлечению данных из изображений. "
        "Посмотри на изображение и извлеки данные для круговой диаграммы. "
        "Определи доли/проценты каждого сегмента. "
        "Верни ТОЛЬКО валидный JSON без пояснений:\n"
        '{"title":"Название диаграммы","labels":["А","Б","В"],"values":[30,50,20]}'
    ),
}

_NUM_HEADERS = {"№", "n", "#", "no", "номер", "num", "п/п", "п.п."}


# ── AI callers ────────────────────────────────────────────────────────────────

def _parse_ai_json(raw: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON; repairs truncated responses."""
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fixed = raw.rstrip().rstrip(",")
        fixed += "]" * max(0, fixed.count("[") - fixed.count("]"))
        fixed += "}" * max(0, fixed.count("{") - fixed.count("}"))
        return json.loads(fixed)


async def _call_gemini(image_bytes: bytes, mime: str, output_type: str) -> dict[str, Any]:
    b64     = base64.standard_b64encode(image_bytes).decode("ascii")
    payload = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": _PROMPTS[output_type]},
        ]}],
        "generationConfig": {
            "maxOutputTokens": AI_MAX_OUTPUT_TOKENS,
            "temperature":     0.0,
        },
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            _GEMINI_ENDPOINT,
            params={"key": _GEMINI_KEY},
            json=payload,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini {resp.status_code}: {resp.text[:400]}")

    logger.info("Gemini response: %d tokens used", resp.json().get("usageMetadata", {}).get("totalTokenCount", 0))
    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_ai_json(raw)


async def _call_claude(image_bytes: bytes, mime: str, output_type: str) -> dict[str, Any]:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=_ANTHROPIC_KEY)
    b64    = base64.standard_b64encode(image_bytes).decode("ascii")
    resp   = await client.messages.create(
        model=AI_CLAUDE_MODEL,
        max_tokens=AI_MAX_OUTPUT_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                {"type": "text",  "text": _PROMPTS[output_type]},
            ],
        }],
    )
    return _parse_ai_json(resp.content[0].text)


async def _call_ai(image_bytes: bytes, mime: str, output_type: str) -> dict[str, Any]:
    """Tries Gemini first (free tier), falls back to Claude. Retries once on failure."""
    if not _GEMINI_KEY and not _ANTHROPIC_KEY:
        raise RuntimeError("Не задан ни GEMINI_API_KEY, ни ANTHROPIC_API_KEY")

    caller   = _call_gemini if _GEMINI_KEY else _call_claude
    last_err: Exception | None = None

    for attempt in range(2):
        try:
            return await caller(image_bytes, mime, output_type)
        except Exception as exc:
            last_err = exc
            if attempt == 0:
                logger.warning("AI attempt 1 failed (%s), retrying in 2s…", exc)
                await asyncio.sleep(2)

    assert last_err is not None
    raise last_err


# ── Excel builders ────────────────────────────────────────────────────────────

_HEADER_FILL = PatternFill("solid", fgColor="1E3A5F")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_BORDER_SIDE = Side(style="thin", color="CCCCCC")
_CELL_BORDER = Border(
    left=_BORDER_SIDE, right=_BORDER_SIDE,
    top=_BORDER_SIDE,  bottom=_BORDER_SIDE,
)


def _auto_col_width(ws: Any, ncols: int, nrows: int) -> None:
    for ci in range(1, ncols + 1):
        width = _COL_MIN_WIDTH
        for ri in range(1, nrows + 3):
            val = ws.cell(ri, ci).value
            if val:
                width = max(width, min(len(str(val)) + _COL_PADDING, _COL_MAX_WIDTH))
        ws.column_dimensions[get_column_letter(ci)].width = width


def _build_table(data: dict[str, Any]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Данные"

    title   = data.get("title", "Таблица")
    headers = data.get("headers", [])
    rows    = data.get("rows", [])
    ncols   = max(len(headers), max((len(r) for r in rows), default=0))

    # Auto-fix row numbering when the first column is an index column
    if headers and str(headers[0]).strip().lower() in _NUM_HEADERS:
        for i, row in enumerate(rows, 1):
            if row:
                row[0] = str(i)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(ncols, 1))
    title_cell            = ws.cell(1, 1, title)
    title_cell.font       = Font(bold=True, size=14, color="1E3A5F")
    title_cell.alignment  = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    for ci, h in enumerate(headers, 1):
        cell           = ws.cell(2, ci, str(h))
        cell.fill      = _HEADER_FILL
        cell.font      = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border    = _CELL_BORDER
    ws.row_dimensions[2].height = 22

    for ri, row in enumerate(rows, 3):
        for ci, val in enumerate(row, 1):
            cell           = ws.cell(ri, ci, val)
            cell.border    = _CELL_BORDER
            cell.alignment = Alignment(wrap_text=True)
            if ri % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F0F4F8")

    _auto_col_width(ws, ncols, len(rows))
    return wb


def _build_chart(data: dict[str, Any]) -> Workbook:
    wb      = Workbook()
    ws_data = wb.active
    ws_data.title = "Данные"

    title       = data.get("title", "График")
    chart_type  = data.get("chart_type", "bar").lower()
    categories  = data.get("categories", [])
    series_list = data.get("series", [])

    ws_data.cell(1, 1, "Категория").font = _HEADER_FONT
    ws_data.cell(1, 1).fill = _HEADER_FILL
    for si, s in enumerate(series_list, 2):
        cell      = ws_data.cell(1, si, s.get("name", f"Серия {si - 1}"))
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL

    for ri, cat in enumerate(categories, 2):
        ws_data.cell(ri, 1, cat)
        for si, s in enumerate(series_list, 2):
            vals = s.get("values", [])
            ws_data.cell(ri, si, vals[ri - 2] if (ri - 2) < len(vals) else None)

    chart = LineChart() if chart_type == "line" else BarChart()
    chart.style          = 10
    chart.title          = title
    chart.y_axis.title   = "Значение"
    if isinstance(chart, BarChart):
        chart.type = "col"

    nrows    = len(categories) + 1
    cats_ref = Reference(ws_data, min_col=1, min_row=2, max_row=nrows)
    for si in range(len(series_list)):
        data_ref = Reference(ws_data, min_col=si + 2, min_row=1, max_row=nrows)
        chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)
    chart.width  = 20
    chart.height = 14

    ws_chart = wb.create_sheet("График")
    ws_chart.add_chart(chart, "B2")
    return wb


def _build_diagram(data: dict[str, Any]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Данные"

    title  = data.get("title", "Диаграмма")
    labels = data.get("labels", [])
    values = data.get("values", [])

    ws.cell(1, 1, "Категория").font = _HEADER_FONT
    ws.cell(1, 1).fill = _HEADER_FILL
    ws.cell(1, 2, "Значение").font = _HEADER_FONT
    ws.cell(1, 2).fill = _HEADER_FILL

    for ri, (label, val) in enumerate(zip(labels, values), 2):
        ws.cell(ri, 1, label)
        ws.cell(ri, 2, val)

    pie       = PieChart()
    pie.title = title
    pie.style = 10

    nrows      = len(labels) + 1
    labels_ref = Reference(ws, min_col=1, min_row=2, max_row=nrows)
    data_ref   = Reference(ws, min_col=2, min_row=1, max_row=nrows)
    pie.add_data(data_ref, titles_from_data=True)
    pie.set_categories(labels_ref)
    pie.width  = 18
    pie.height = 14

    ws_chart = wb.create_sheet("Диаграмма")
    ws_chart.add_chart(pie, "B2")
    return wb


_BUILDERS: dict[str, Any] = {
    "table":   _build_table,
    "chart":   _build_chart,
    "diagram": _build_diagram,
}

_TYPE_RU: dict[str, str] = {
    "table":   "таблица",
    "chart":   "график",
    "diagram": "диаграмма",
}


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
        if output_type not in _BUILDERS:
            output_type = "table"

        image_bytes  = await photo.read()
        content_type = photo.content_type or "image/jpeg"
        if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            content_type = "image/jpeg"

        data = await _call_ai(image_bytes, content_type, output_type)
        wb   = _BUILDERS[output_type](data)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        raw_title   = data.get("title", "data")
        ascii_title = re.sub(r"[^\w\- ]", "", raw_title, flags=re.ASCII)[:40].strip() or "data"
        filename    = f"{ascii_title}_{output_type}.xlsx"
        encoded     = urllib.parse.quote(f"{raw_title[:40]}_{_TYPE_RU[output_type]}.xlsx")
        disposition = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded}'

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": disposition},
        )
    except Exception as exc:
        logger.error("photo-to-excel error: %s", exc, exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)
