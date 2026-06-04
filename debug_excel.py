"""Диагностика — показывает что именно читает импортёр из демо-файла."""
import io, openpyxl

path = r"C:\Users\HUAWEI\Downloads\Констракшн_DEMO_2026.xlsx"
wb = openpyxl.load_workbook(path, data_only=True)

print("=== ЛИСТЫ В ФАЙЛЕ ===")
for i, ws in enumerate(wb.worksheets):
    print(f"  [{i}] '{ws.title}'")

print()

# Симулируем логику поиска нужных листов
target_sheets = [ws for ws in wb.worksheets
                 if ws.title.strip() in ('2026', '2027')
                 or '2026' in ws.title or '2027' in ws.title]
if not target_sheets:
    target_sheets = [wb.worksheets[-1]]
    print("!!! Листов '2026'/'2027' не найдено — берём последний лист")

for ws in target_sheets:
    print(f"\n=== ЛИСТ: '{ws.title}' ===")

    # Ищем header_row
    header_row = 4
    for r in range(1, 11):
        for c in range(1, 15):
            v = str(ws.cell(r, c).value or '')
            if 'Номер' in v or 'Адрес' in v:
                header_row = r
                print(f"  header_row = {r}  (ячейка R{r}C{c} = '{v}')")
                break
        else:
            continue
        break

    print(f"\n  Сканирую заголовки (строки {max(1,header_row-1)}–{header_row+1}):")
    col = {}
    for r in range(max(1, header_row - 1), header_row + 2):
        for c in range(1, 60):
            v = str(ws.cell(r, c).value or '').strip()
            vl = v.lower()
            if not v:
                continue
            if ('номер тк' in vl or vl == 'тк') and 'tk' not in col:
                col['tk'] = c; print(f"    tk      -> col {c}: '{v}'")
            elif 'адрес' in vl and 'addr' not in col and len(v) < 30:
                col['addr'] = c; print(f"    addr    -> col {c}: '{v}'")
            elif 'тип формата' in vl and 'fmt' not in col:
                col['fmt'] = c; print(f"    fmt     -> col {c}: '{v}'")
            elif ('формат' in vl and len(v) < 20) and 'fmt' not in col:
                col['fmt'] = c; print(f"    fmt(2)  -> col {c}: '{v}'")
            elif ('регион' in vl or 'город' in vl) and 'city' not in col:
                col['city'] = c; print(f"    city    -> col {c}: '{v}'")
            elif 'площадь' in vl and 'тз' in vl and 'area' not in col:
                col['area'] = c; print(f"    area    -> col {c}: '{v}'")
            elif ('приёмка' in vl or 'приемка' in vl) and 'reception' not in col:
                col['reception'] = c; print(f"    reception -> col {c}: '{v}'")
            elif 'выход на смр' in vl and 'cmp' not in col:
                col['cmp'] = c; print(f"    cmp     -> col {c}: '{v}'")
            elif vl.startswith('впк') and 'vpk' not in col:
                col['vpk'] = c; print(f"    vpk     -> col {c}: '{v}'")
            elif 'первоначальная' in vl and 'open_plan' not in col:
                col['open_plan'] = c; print(f"    open_plan -> col {c}: '{v}'")
            elif 'фактическая' in vl and 'open_fact' not in col:
                col['open_fact'] = c; print(f"    open_fact -> col {c}: '{v}'")
            elif 'менеджер' in vl and 'ос' in vl and 'mgr_os' not in col:
                col['mgr_os'] = c; print(f"    mgr_os  -> col {c}: '{v}'")

    col.setdefault('tk', 2)
    col.setdefault('addr', 3)
    col.setdefault('mgr_os', 38)
    col.setdefault('open_plan', 20)
    col.setdefault('open_fact', 21)
    fmt_from_header = 'fmt' in col

    print(f"\n  fmt_from_header = {fmt_from_header}")
    print(f"\n  Итоговые колонки: {col}")

    print(f"\n  Первые 5 строк данных (начиная с {header_row+1}):")
    for row_idx in range(header_row + 1, min(header_row + 6, ws.max_row + 1)):
        tk_val  = ws.cell(row_idx, col['tk']).value
        fmt_val = ws.cell(row_idx, col.get('fmt', 5)).value if col.get('fmt') else None
        mgr_val = ws.cell(row_idx, col['mgr_os']).value
        plan    = ws.cell(row_idx, col['open_plan']).value
        print(f"    row {row_idx}: tk={tk_val!r:10}  fmt={fmt_val!r:6}  mgr={mgr_val!r:20}  plan={plan!r}")
