"""Photo → Excel conversion tool. Admin-only during development."""
import base64
import io
import json
import logging
import os
import re

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from deps import require_admin, templates

logger = logging.getLogger(__name__)
router = APIRouter()

_GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_PROMPTS = {
    "table": (
        "Ты эксперт по извлечению данных из изображений. "
        "Посмотри на изображение и извлеки ВСЕ данные в формате таблицы. "
        "Верни ТОЛЬКО валидный JSON без пояснений:\n"
        '{"title":"Название таблицы","headers":["Столбец1","Столбец2"],'
        '"rows":[["значение1","значение2"],["значение3","значение4"]]}'
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


def _call_gemini(image_bytes: bytes, mime: str, output_type: str) -> dict:
    import urllib.error
    import urllib.request

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    payload = json.dumps({
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": mime, "data": b64}},
                {"text": _PROMPTS[output_type]},
            ]
        }],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.1},
    }).encode()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={_GEMINI_KEY}"
    )
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini {e.code}: {body[:400]}") from e
    raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _call_claude(image_bytes: bytes, mime: str, output_type: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                {"type": "text", "text": _PROMPTS[output_type]},
            ],
        }],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _call_ai(image_bytes: bytes, mime: str, output_type: str) -> dict:
    """Try Gemini first (free), fall back to Claude if GEMINI_API_KEY not set."""
    if _GEMINI_KEY:
        return _call_gemini(image_bytes, mime, output_type)
    if _ANTHROPIC_KEY:
        return _call_claude(image_bytes, mime, output_type)
    raise RuntimeError("Не задан ни GEMINI_API_KEY, ни ANTHROPIC_API_KEY")


# ── Excel builders ────────────────────────────────────────────────────────────

_HEADER_FILL = PatternFill("solid", fgColor="1E3A5F")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_BORDER_SIDE = Side(style="thin", color="CCCCCC")
_CELL_BORDER = Border(
    left=_BORDER_SIDE, right=_BORDER_SIDE,
    top=_BORDER_SIDE, bottom=_BORDER_SIDE,
)
_ACCENT = "3CB34A"  # Lenta green


def _build_table(data: dict) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Данные"

    title = data.get("title", "Таблица")
    headers = data.get("headers", [])
    rows = data.get("rows", [])
    ncols = max(len(headers), max((len(r) for r in rows), default=0))

    # Title row
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(ncols, 1))
    tc = ws.cell(1, 1, title)
    tc.font = Font(bold=True, size=14, color="1E3A5F")
    tc.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    # Headers
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(2, ci, str(h))
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _CELL_BORDER
    ws.row_dimensions[2].height = 22

    # Data rows
    for ri, row in enumerate(rows, 3):
        for ci, val in enumerate(row, 1):
            cell = ws.cell(ri, ci, val)
            cell.border = _CELL_BORDER
            cell.alignment = Alignment(wrap_text=True)
            if ri % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F0F4F8")

    # Auto column width
    for ci in range(1, ncols + 1):
        max_w = 12
        for ri in range(1, len(rows) + 3):
            v = ws.cell(ri, ci).value
            if v:
                max_w = max(max_w, min(len(str(v)) + 4, 40))
        ws.column_dimensions[get_column_letter(ci)].width = max_w

    return wb


def _build_chart(data: dict) -> Workbook:
    wb = Workbook()
    ws_data = wb.active
    ws_data.title = "Данные"

    title = data.get("title", "График")
    chart_type = data.get("chart_type", "bar").lower()
    categories = data.get("categories", [])
    series_list = data.get("series", [])

    # Write data table
    ws_data.cell(1, 1, "Категория").font = _HEADER_FONT
    ws_data.cell(1, 1).fill = _HEADER_FILL
    for si, s in enumerate(series_list, 2):
        cell = ws_data.cell(1, si, s.get("name", f"Серия {si-1}"))
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL

    for ri, cat in enumerate(categories, 2):
        ws_data.cell(ri, 1, cat)
        for si, s in enumerate(series_list, 2):
            vals = s.get("values", [])
            ws_data.cell(ri, si, vals[ri - 2] if (ri - 2) < len(vals) else None)

    # Create chart
    if chart_type == "line":
        chart = LineChart()
        chart.style = 10
    else:
        chart = BarChart()
        chart.type = "col"
        chart.style = 10

    chart.title = title
    chart.y_axis.title = "Значение"
    chart.x_axis.title = ""

    nrows = len(categories) + 1
    cats_ref = Reference(ws_data, min_col=1, min_row=2, max_row=nrows)

    for si in range(len(series_list)):
        data_ref = Reference(ws_data, min_col=si + 2, min_row=1, max_row=nrows)
        chart.add_data(data_ref, titles_from_data=True)

    chart.set_categories(cats_ref)
    chart.shape = 4
    chart.width = 20
    chart.height = 14

    ws_chart = wb.create_sheet("График")
    ws_chart.add_chart(chart, "B2")

    return wb


def _build_diagram(data: dict) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Данные"

    title = data.get("title", "Диаграмма")
    labels = data.get("labels", [])
    values = data.get("values", [])

    # Write data
    ws.cell(1, 1, "Категория").font = _HEADER_FONT
    ws.cell(1, 1).fill = _HEADER_FILL
    ws.cell(1, 2, "Значение").font = _HEADER_FONT
    ws.cell(1, 2).fill = _HEADER_FILL

    for ri, (label, val) in enumerate(zip(labels, values), 2):
        ws.cell(ri, 1, label)
        ws.cell(ri, 2, val)

    # Pie chart
    pie = PieChart()
    pie.title = title
    pie.style = 10

    nrows = len(labels) + 1
    labels_ref = Reference(ws, min_col=1, min_row=2, max_row=nrows)
    data_ref   = Reference(ws, min_col=2, min_row=1, max_row=nrows)
    pie.add_data(data_ref, titles_from_data=True)
    pie.set_categories(labels_ref)
    pie.dataLabels = None
    pie.width = 18
    pie.height = 14

    ws_chart = wb.create_sheet("Диаграмма")
    ws_chart.add_chart(pie, "B2")

    return wb


_BUILDERS = {
    "table":   _build_table,
    "chart":   _build_chart,
    "diagram": _build_diagram,
}

_TYPE_NAMES = {
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


@router.get("/api/tools/gemini-test", response_class=HTMLResponse)
async def gemini_test(request: Request, user: dict = Depends(require_admin)):
    """Diagnostic: test Gemini API key and list available models."""
    try:
        import urllib.request as ur
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={_GEMINI_KEY}&pageSize=50"
        with ur.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        names = [m["name"] for m in data.get("models", [])]
        return HTMLResponse(f"<pre>KEY set: {bool(_GEMINI_KEY)}\nModels:\n" + "\n".join(names) + "</pre>")
    except Exception as e:
        return HTMLResponse(f"<pre>ERROR: {e}</pre>", status_code=500)


@router.post("/api/tools/photo-to-excel")
async def photo_to_excel_api(
    request: Request,
    user: dict = Depends(require_admin),
    photo: UploadFile = File(...),
    output_type: str = Form("table"),
):
    try:
        if output_type not in _BUILDERS:
            output_type = "table"

        image_bytes = await photo.read()
        content_type = photo.content_type or "image/jpeg"
        if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            content_type = "image/jpeg"

        data = _call_ai(image_bytes, content_type, output_type)

        wb = _BUILDERS[output_type](data)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        safe_title = re.sub(r"[^\w\- ]", "", data.get("title", "data"))[:40].strip() or "data"
        filename = f"{safe_title}_{_TYPE_NAMES[output_type]}.xlsx"

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("photo-to-excel error: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)
