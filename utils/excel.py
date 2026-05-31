from datetime import datetime, date


def safe_date(val):
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return None


def row_to_dict(row) -> dict:
    return {cell.column: cell.value for cell in row if cell.value is not None}


def match_manager(name_str: str, managers: list) -> int | None:
    """Match 'Месмер Д.' / 'МЕСМЕР' to manager id by last name."""
    if not name_str or not isinstance(name_str, str):
        return None
    last_name = name_str.strip().split()[0].strip('.')
    if not last_name or len(last_name) < 3:
        return None
    last_lower = last_name.lower()
    for m in managers:
        m_last = m.name.split()[0].lower()
        if m_last == last_lower or m_last.startswith(last_lower) or last_lower.startswith(m_last):
            return m.id
    return None
