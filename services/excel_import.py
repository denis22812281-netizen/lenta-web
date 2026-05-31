"""Excel import functions for Реконструкции and Констракшн."""
import io
from datetime import datetime, date

import openpyxl
from sqlalchemy.orm import Session

import models
from config import STAGE_NAMES
from utils.excel import safe_date, row_to_dict, match_manager


def import_reconstruct_excel(content: bytes, db: Session) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    managers = db.query(models.Manager).all()
    today = date.today()
    created = updated = 0

    sheet_configs = [
        (9,  4, 1, 3, 5, 9, 12, 41, 52, 51, "Реконструкция"),
        (10, 4, 1, 3, 5, 9, 12, 37, 42, 41, "Реконструкция"),
        (11, 3, 1, 2, 3, 6,  7,  8, 41, 40, "Реконструкция"),
        (12, 3, 1, 2, 3, 5,  7,  8, 37, 40, "Реконструкция"),
    ]
    stage_map_main = {
        "СИД": (14, 15), "Зонирование": (16, 17), "Закрытие": (18, 19),
        "ВПК1": (34, 35), "Открытие": (40, 41),
    }
    stage_map_risk = {
        "СИД": (9, 10), "Зонирование": (11, 12), "Закрытие": (13, 14),
        "ВПК1": (15, 16), "Открытие": (8, None),
    }

    for cfg in sheet_configs:
        idx, start_row, c_tk, c_region, c_addr, c_type, c_area, c_deadline, c_mgr, c_mgr2, p_type = cfg
        if idx >= len(wb.worksheets):
            continue
        ws = wb.worksheets[idx]
        is_risk = idx in (11, 12)
        stage_map = stage_map_risk if is_risk else stage_map_main

        for row_idx in range(start_row, ws.max_row + 1):
            row = ws[row_idx]
            vals = row_to_dict(row)

            tk = vals.get(c_tk)
            if not tk or not isinstance(tk, (int, float)):
                continue
            tk_num = str(int(tk))

            region = vals.get(c_region, "")
            full_address = str(vals.get(c_addr, "") or "").strip()
            area = vals.get(c_area)
            area = float(area) if isinstance(area, (int, float)) else None

            city = ""
            if region and isinstance(region, str) and region not in ("#REF!", "#N/A"):
                city = region
            elif full_address:
                city = full_address.split(",")[0].strip()

            dl_val = vals.get(c_deadline)
            deadline = safe_date(dl_val)
            if deadline is None:
                dates = [safe_date(v) for v in vals.values() if safe_date(v)]
                deadline = max(dates) if dates else None

            mgr_val = vals.get(c_mgr, "")
            manager_id = match_manager(str(mgr_val) if mgr_val else "", managers)
            if not manager_id:
                mgr_val2 = vals.get(c_mgr2, "")
                manager_id = match_manager(str(mgr_val2) if mgr_val2 else "", managers)

            sid_s  = safe_date(vals.get(stage_map["СИД"][0]))
            sid_e  = safe_date(vals.get(stage_map["СИД"][1]))
            zon_s  = safe_date(vals.get(stage_map["Зонирование"][0]))
            zon_e  = safe_date(vals.get(stage_map["Зонирование"][1]))
            clos   = safe_date(vals.get(stage_map["Закрытие"][0]))
            vpk    = safe_date(vals.get(stage_map["ВПК1"][0]))
            open_end = stage_map["Открытие"][1]
            opening  = safe_date(vals.get(open_end if open_end else stage_map["Открытие"][0]))

            proj_start = sid_s
            proj_name  = f"ТК {tk_num}" + (f" {city}" if city else "")
            status = "Завершён" if (opening and opening <= today) else "Активный"

            existing = db.query(models.Project).filter(
                models.Project.tk_number == tk_num).first()

            if existing:
                existing.city          = city or existing.city
                existing.address       = full_address or existing.address
                existing.project_type  = p_type
                existing.start_date    = proj_start or existing.start_date
                existing.end_date      = deadline or existing.end_date
                existing.area          = area or existing.area
                existing.sid_start     = sid_s  or existing.sid_start
                existing.sid_end       = sid_e  or existing.sid_end
                existing.zoning_start  = zon_s  or existing.zoning_start
                existing.zoning_end    = zon_e  or existing.zoning_end
                existing.closure_date  = clos   or existing.closure_date
                existing.vpk_date      = vpk    or existing.vpk_date
                existing.opening_date  = opening or existing.opening_date
                if existing.status != "Приостановлен":
                    existing.status = status
                if manager_id and not existing.manager_id:
                    existing.manager_id = manager_id
                updated += 1
            else:
                db.add(models.Project(
                    name=proj_name, tk_number=tk_num, city=city,
                    address=full_address, project_type=p_type,
                    manager_id=manager_id, status=status,
                    start_date=proj_start, end_date=deadline, area=area,
                    sid_start=sid_s, sid_end=sid_e,
                    zoning_start=zon_s, zoning_end=zon_e,
                    closure_date=clos, vpk_date=vpk, opening_date=opening,
                ))
                created += 1

        db.flush()

    db.commit()
    return {"created": created, "updated": updated}


def import_construction_excel(content: bytes, db: Session) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    managers = db.query(models.Manager).all()
    today = date.today()
    created = updated = 0

    target_sheets = [ws for ws in wb.worksheets
                     if ws.title.strip() in ('2026', '2027')
                     or '2026' in ws.title or '2027' in ws.title]
    seen = set()
    target_sheets = [ws for ws in target_sheets
                     if ws.title not in seen and not seen.add(ws.title)]
    if not target_sheets:
        target_sheets = [wb.worksheets[-1]]

    skipped_fmt = skipped_mgr = rows_with_tk = 0
    sample_formats: set = set()
    sample_managers: set = set()

    for ws in target_sheets:
        header_row = 4
        found_hdr = False
        for r in range(1, 11):
            if found_hdr:
                break
            for c in range(1, 15):
                v = str(ws.cell(r, c).value or '')
                if 'Номер' in v or 'Адрес' in v:
                    header_row = r
                    found_hdr = True
                    break

        col: dict = {}
        for r in range(max(1, header_row - 1), header_row + 2):
            for c in range(1, 60):
                v = str(ws.cell(r, c).value or '').strip()
                vl = v.lower()
                if not v:
                    continue
                if ('номер тк' in vl or vl == 'тк') and 'tk' not in col:
                    col['tk'] = c
                elif 'адрес' in vl and 'addr' not in col and len(v) < 30:
                    col['addr'] = c
                elif 'тип формата' in vl and 'fmt' not in col:
                    col['fmt'] = c
                elif ('формат' in vl and len(v) < 20) and 'fmt' not in col:
                    col['fmt'] = c
                elif ('регион' in vl or 'город' in vl) and 'city' not in col:
                    col['city'] = c
                elif 'площадь' in vl and 'тз' in vl and 'area' not in col:
                    col['area'] = c
                elif ('приёмка' in vl or 'приемка' in vl) and 'reception' not in col:
                    col['reception'] = c
                elif 'выход на смр' in vl and 'cmp' not in col:
                    col['cmp'] = c
                elif vl.startswith('впк') and 'vpk' not in col:
                    col['vpk'] = c
                elif 'первоначальная' in vl and 'open_plan' not in col:
                    col['open_plan'] = c
                elif 'фактическая' in vl and 'open_fact' not in col:
                    col['open_fact'] = c
                elif 'статус' in vl and ('откр' in vl or 'open' in vl) and 'open_status' not in col:
                    col['open_status'] = c
                elif 'менеджер' in vl and 'ос' in vl and 'mgr_os' not in col:
                    col['mgr_os'] = c

        fmt_from_header = 'fmt' in col
        col.setdefault('tk', 2)
        col.setdefault('addr', 3)
        col.setdefault('reception', 14)
        col.setdefault('cmp', 16)
        col.setdefault('vpk', 19)
        col.setdefault('open_plan', 20)
        col.setdefault('open_fact', 21)
        col.setdefault('open_status', 22)
        col.setdefault('mgr_os', 38)

        for row_idx in range(header_row + 1, ws.max_row + 1):
            tk_val = ws.cell(row_idx, col['tk']).value
            if not tk_val:
                continue
            tk_num = str(tk_val).strip()
            if not tk_num or tk_num in ('None', 'Номер ТК', 'ТК') or len(tk_num) > 20:
                continue

            rows_with_tk += 1
            address  = str(ws.cell(row_idx, col['addr']).value or '').strip()
            fmt_type = str(ws.cell(row_idx, col['fmt']).value or '').strip() if col.get('fmt') else ''
            if fmt_type and len(sample_formats) < 8:
                sample_formats.add(fmt_type)
            mgr_raw = str(ws.cell(row_idx, col['mgr_os']).value or '').strip()
            if mgr_raw and len(sample_managers) < 8:
                sample_managers.add(mgr_raw)
            city = str(ws.cell(row_idx, col['city']).value or '').strip() if col.get('city') else ''
            area_val = ws.cell(row_idx, col['area']).value if col.get('area') else None
            area = float(area_val) if isinstance(area_val, (int, float)) else None

            reception = safe_date(ws.cell(row_idx, col['reception']).value)
            cmp_date  = safe_date(ws.cell(row_idx, col['cmp']).value)
            vpk_date  = safe_date(ws.cell(row_idx, col['vpk']).value)
            open_plan = safe_date(ws.cell(row_idx, col['open_plan']).value)
            open_fact = safe_date(ws.cell(row_idx, col['open_fact']).value)
            open_st   = str(ws.cell(row_idx, col['open_status']).value or '').strip()

            manager_id = match_manager(mgr_raw, managers)

            fmt_upper = fmt_type.upper()
            if fmt_from_header and fmt_type and fmt_upper not in ('SM', 'UTKONOS'):
                skipped_fmt += 1
                continue
            if not manager_id:
                skipped_mgr += 1
                continue

            opening = open_fact or open_plan
            status  = "Завершён" if (opening and opening <= today) else "Активный"
            proj_name = f"ТК {tk_num}" + (f" {city}" if city else "")

            existing = db.query(models.Project).filter(
                models.Project.tk_number == tk_num,
                models.Project.project_type == "Констракшн"
            ).first()
            if existing:
                existing.address      = address   or existing.address
                existing.city         = city       or existing.city
                existing.area         = area       or existing.area
                existing.format_type  = fmt_type   or existing.format_type
                existing.open_status  = open_st    or existing.open_status
                existing.start_date   = reception  or existing.start_date
                existing.closure_date = cmp_date   or existing.closure_date
                existing.vpk_date     = vpk_date   or existing.vpk_date
                existing.end_date     = open_plan  or existing.end_date
                existing.opening_date = open_fact  or existing.opening_date
                if existing.status != "Приостановлен":
                    existing.status = status
                existing.manager_id = manager_id
                updated += 1
            else:
                db.add(models.Project(
                    name=proj_name, tk_number=tk_num,
                    city=city, address=address,
                    project_type="Констракшн",
                    manager_id=manager_id, status=status,
                    format_type=fmt_type, open_status=open_st,
                    start_date=reception, closure_date=cmp_date,
                    vpk_date=vpk_date, end_date=open_plan,
                    opening_date=open_fact, area=area,
                ))
                created += 1

    db.commit()
    return {
        "created": created, "updated": updated,
        "sheets": ", ".join(ws.title for ws in target_sheets),
        "rows_with_tk": rows_with_tk,
        "skipped_fmt": skipped_fmt, "skipped_mgr": skipped_mgr,
        "sample_formats": sorted(sample_formats),
        "sample_managers": sorted(sample_managers),
    }


def parse_excel_file(content: bytes, project_type: str,
                     manager_id_default: int | None, db: Session) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    created = updated = 0

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        project_name = sheet_name
        tk_num = city_name = ""

        for row in ws.iter_rows(max_row=10, values_only=True):
            for cell in row:
                if cell and isinstance(cell, str):
                    text = cell.strip()
                    if text.upper().startswith(("ТК", "TK")):
                        project_name = text
                        parts = text.split()
                        if len(parts) >= 2:
                            tk_num = parts[1]
                        if len(parts) >= 3:
                            city_name = " ".join(parts[2:])

        all_dates = []
        for row in ws.iter_rows(max_row=100, values_only=True):
            for cell in row:
                d = safe_date(cell)
                if d:
                    all_dates.append(d)

        proj_start = min(all_dates) if all_dates else None
        proj_end   = max(all_dates) if all_dates else None

        existing = None
        if tk_num:
            existing = db.query(models.Project).filter(
                models.Project.tk_number == tk_num).first()
        if not existing and project_name:
            existing = db.query(models.Project).filter(
                models.Project.name == project_name).first()

        if existing:
            if proj_start:
                existing.start_date = proj_start
            if proj_end:
                existing.end_date = proj_end
            if city_name and not existing.city:
                existing.city = city_name
            if project_type and not existing.project_type:
                existing.project_type = project_type
            db.flush()
            _sync_stages(ws, existing.id, db)
            updated += 1
        else:
            p = models.Project(
                name=project_name, tk_number=tk_num, city=city_name,
                project_type=project_type,
                manager_id=manager_id_default,
                status="Активный", start_date=proj_start, end_date=proj_end,
            )
            db.add(p)
            db.flush()
            _sync_stages(ws, p.id, db)
            created += 1

    db.commit()
    return {"created": created, "updated": updated}


def _sync_stages(ws, project_id: int, db: Session):
    existing_names = {s.name for s in db.query(models.ProjectStage).filter(
        models.ProjectStage.project_id == project_id).all()}
    order = db.query(models.ProjectStage).filter(
        models.ProjectStage.project_id == project_id).count()

    for row in ws.iter_rows(values_only=True):
        if not row[0] or not isinstance(row[0], str):
            continue
        cell_text = row[0].strip()
        for sn in STAGE_NAMES:
            if sn.split()[0].lower() in cell_text.lower():
                start = end = None
                for v in row[1:]:
                    d = safe_date(v)
                    if d and not start:
                        start = d
                    elif d and not end:
                        end = d
                        break
                if cell_text not in existing_names:
                    db.add(models.ProjectStage(
                        project_id=project_id, name=cell_text,
                        start_date=start, end_date=end, order=order))
                    order += 1
                else:
                    s = db.query(models.ProjectStage).filter(
                        models.ProjectStage.project_id == project_id,
                        models.ProjectStage.name == cell_text).first()
                    if s:
                        if start:
                            s.start_date = start
                        if end:
                            s.end_date = end
                break
