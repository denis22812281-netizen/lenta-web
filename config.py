# ── AI models ────────────────────────────────────────────────────────────────
AI_GEMINI_MODEL     = "gemini-2.5-flash"
AI_CLAUDE_MODEL     = "claude-opus-4-8"
AI_MAX_OUTPUT_TOKENS = 16_384

# ── Manager seed + derived display order ─────────────────────────────────────
PROJECT_TYPES = [
    "Реконструкция", "Констракшн", "КСО",
    "Новое строительство", "Капитальный ремонт", "Техническое обслуживание",
]
STATUSES       = ["Активный", "Завершён", "Приостановлен", "Планирование"]
PRIORITIES     = ["Высокий", "Средний", "Низкий"]
TASK_STATUSES  = ["Открытая", "В работе", "На проверке", "Завершена"]
STAGE_NAMES    = [
    "Подготовительный этап",
    "Демонтажные работы",
    "Фундаментные работы",
    "Конструктивные элементы",
    "Инженерные системы",
    "Чистовая отделка",
    "Благоустройство",
    "Сдача объекта",
]
MANAGERS_SEED: list[tuple[str, bool]] = [
    ("Гаврин Игорь",       True),
    ("Комаров Алексей",    True),
    ("Месмер Денис",       False),
    ("Митько Роберт",      False),
    ("Ловчиков Александр", False),
    ("Шевченко Наталья",   False),
    ("Хачатурова Жанна",   False),
    ("Валеев Борис",       False),
    ("Студеникин Сергей",  False),
    ("Косило Сергей",      False),
]

# Pre-computed display orders derived from MANAGERS_SEED (single source of truth)
MANAGER_LEADER_ORDER    = [n for n, is_leader in MANAGERS_SEED if is_leader]
MANAGER_NONLEADER_ORDER = [n for n, is_leader in MANAGERS_SEED if not is_leader]
