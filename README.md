# Лента.PM — Система управления проектами

Внутренняя операционная система для дирекции строительства ЛЕНТА.  
Управляет открытиями магазинов, реконструкциями, задачами, ВПК-отчётами и командой.

---

## Возможности

| Модуль | Функции |
|--------|---------|
| **Проекты** | Реконструкции и констракшн: статусы, этапы, дедлайны, история, вложения, комментарии, экспорт Excel |
| **Gantt** | Интерактивная диаграмма Ганта с drag-and-drop (frappe-gantt) |
| **Задачи** | Постановка с приоритетами, исполнителями, дедлайнами, фото |
| **ВПК-отчёты** | Чеклисты ВПК-1/ВПК-2 с фото, экспорт Excel, учёт прочтения, галерея открытий |
| **Адаптационные карточки** | Цифровые анкеты на основе XLSX-шаблона + фото объекта |
| **График СМР** | Временная шкала с вехами, email-подтверждения, push-уведомления |
| **Чат** | Личные и общий чат с фото, онлайн-статусы, push-уведомления |
| **ИИ-конвертер** | Фото/текст → Excel (таблица, диаграмма, Ганта, сравнение, объединение) |
| **ИИ-ассистент** | Claude / Groq / Gemini с контекстом проектов |
| **Дедлайны** | Единый экран всех сроков по реконструкции и констракшн |
| **КСО** | Объекты соцответственности, готовность, комментарии |
| **Аналитика** | Дашборд открытий, просрочки, статистика по менеджерам |
| **PWA** | Устанавливается как приложение, push-уведомления, offline |

---

## Технологии

- **Backend:** Python 3.11+ / FastAPI 0.115 / SQLAlchemy 2.0
- **Frontend:** Jinja2 + Bootstrap 5.3 + Vanilla JS (без фреймворков)
- **БД:** PostgreSQL (production) / SQLite (локальная разработка)
- **Хранилище фото:** Cloudinary (auto-quality, auto-format)
- **Email:** Brevo (SMTP + API)
- **Push:** Web Push API / VAPID / pywebpush
- **AI:** Gemini (фото→Excel), Claude/Groq/DeepSeek (чат-ассистент)
- **Деплой:** Railway.app (автодеплой при push в main)
- **Тесты:** pytest + pytest-asyncio — 152 теста (E2E запуск: `pytest -m e2e`)

---

## Быстрый старт (локально)

```bash
# 1. Клонировать
git clone <repo-url> && cd lenta-web

# 2. Виртуальное окружение
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # Linux/Mac

# 3. Зависимости
pip install -r requirements.txt

# 4. Минимальный .env
SECRET_KEY=local-dev-key-32-chars-minimum
DATABASE_URL=sqlite:///./lenta.db
ADMIN_PHONE=+79997303914

# 5. Запуск
uvicorn main:app --reload
# Открыть: http://localhost:8000
```

Войти с номером из `ADMIN_PHONE` → создать пароль при первом входе.

---

## Тесты

```bash
pytest                          # 152 unit-теста (E2E исключены по умолчанию)
pytest -m e2e                   # E2E тесты (нужен запущенный сервер + Playwright)
pytest tests/test_auth.py -v    # один модуль
```

Тесты используют SQLite в памяти — PostgreSQL не нужен. `TESTING=1` отключает CSRF.

---

## Переменные окружения

Все переменные описаны в `.env.example`. Ниже — минимальный набор по группам.

### Обязательные

| Переменная | Описание |
|-----------|---------|
| `SECRET_KEY` | Секрет сессий, минимум 32 символа. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` или `sqlite:///./lenta.db` для локальной разработки |
| `ADMIN_PHONE` | Телефон первого администратора (+7XXXXXXXXXX) |

### Email (Brevo)

| Переменная | Описание |
|-----------|---------|
| `SMTP_HOST` | `smtp-relay.brevo.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Логин из Brevo |
| `SMTP_PASS` | SMTP-ключ из Brevo |
| `SMTP_FROM` | `Лента.PM <noreply@ваш-домен.ru>` |
| `BREVO_API_KEY` | API-ключ для Brevo (транзакционные письма) |
| `NOTIFY_PRECHECK_EMAIL` | Адрес для уведомлений о предосмотрах ВПК |
| `NOTIFY_ERROR_EMAIL` | Адрес для уведомлений об ошибках сервера |
| `NOTIFY_OVERRIDE_EMAIL` | Режим тестирования: все письма → только этот адрес |

### Push-уведомления (VAPID)

```bash
# Сгенерировать ключи один раз:
python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print('PRIVATE:', v.private_key); print('PUBLIC:', v.public_key)"
```

| Переменная | Описание |
|-----------|---------|
| `VAPID_PRIVATE_KEY` | Приватный VAPID-ключ |
| `VAPID_PUBLIC_KEY` | Публичный VAPID-ключ |
| `APP_URL` | `https://ваш-домен.up.railway.app` (для push payload) |

### AI-сервисы (опционально)

| Переменная | Сервис | Получить |
|-----------|--------|---------|
| `GEMINI_API_KEY` | Фото→Excel | aistudio.google.com |
| `ANTHROPIC_API_KEY` | Claude-ассистент + fallback для фото | anthropic.com |
| `GROQ_API_KEY` | Быстрый текстовый AI | console.groq.com |
| `DEEPSEEK_API_KEY` | Альтернативный AI | platform.deepseek.com |

### Хранилище фото (Cloudinary)

| Переменная | Описание |
|-----------|---------|
| `CLOUDINARY_CLOUD_NAME` | Cloud name из Cloudinary Dashboard |
| `CLOUDINARY_API_KEY` | API Key |
| `CLOUDINARY_API_SECRET` | API Secret |

### Мониторинг (опционально)

| Переменная | Описание |
|-----------|---------|
| `SENTRY_DSN` | DSN из Sentry.io для трекинга ошибок |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` (по умолчанию `INFO`) |

---

## Деплой на Railway

### Первый деплой

```bash
# Установить Railway CLI
npm install -g @railway/cli
railway login
railway init
railway up
```

### Автодеплой (GitHub Actions)

В GitHub → Settings → Secrets добавить `RAILWAY_TOKEN` (из Railway Dashboard → Account → Tokens).  
После этого каждый push в `main` → тесты → автодеплой.

### Обновление

Просто `git push` — Railway подхватит автоматически. Миграции БД запускаются при старте приложения (`migrations.py`).

---

## Добавить пользователя

1. Войти как администратор
2. Перейти в `/admin/users`
3. Нажать «Добавить» → ввести номер телефона `+7XXXXXXXXXX`, имя, галочку «Администратор» если нужно
4. Пользователь при первом входе создаёт пароль самостоятельно

---

## Структура проекта

```
lenta-web/
├── main.py               # Точка входа, middleware, роутеры, startup
├── deps.py               # Shared зависимости (auth, templates, limiter)
├── database.py           # SQLAlchemy engine, get_db
├── config.py             # Константы (типы проектов, статусы, команда)
├── migrations.py         # Идемпотентные SQL-миграции (запускаются при старте)
├── worker.py             # Standalone worker (backup, APScheduler)
├── middleware.py         # CSRF, security headers
│
├── models/               # SQLAlchemy модели
│   ├── auth.py           # User, PhoneWhitelist, AuditLog
│   ├── project.py        # Project, ProjectStage, ProjectHistory, Attachment
│   ├── task.py           # Task
│   ├── vpk.py            # VpkReport, VpkCriteria, OpeningPhoto
│   ├── smr.py            # SmrProject, SmrTask
│   ├── recon.py          # ReconProject (реконструкция/констракшн)
│   ├── adaptation.py     # AdaptationCard
│   └── misc.py           # ChatMessage, PushSubscription, ConversionTemplate, …
│
├── routes/               # FastAPI роутеры (по одному на модуль)
│   ├── auth.py           # /login, /logout, /qr
│   ├── projects.py       # /projects, /api/projects
│   ├── vpk.py            # /vpk, /api/vpk
│   ├── smr.py            # /smr, /api/smr
│   ├── tools.py          # /tools, /api/tools (AI-конвертер)
│   ├── admin.py          # /admin
│   └── …                 # chat, tasks, deadlines, kso, adaptation, …
│
├── services/             # Бизнес-логика
│   ├── tools_service.py  # AI-вызовы + Excel builders (build_table, build_gantt, …)
│   ├── push_service.py   # Web Push / VAPID
│   ├── email_service.py  # Brevo SMTP
│   ├── excel_import.py   # Парсинг XLSX → Project
│   ├── cloud_storage.py  # Cloudinary upload/delete
│   └── background.py     # Async фоновые задачи
│
├── templates/            # Jinja2 HTML-шаблоны
├── static/
│   ├── css/style.css     # ~1000 строк кастомного CSS
│   ├── js/app.js         # Toast, theme, deadlines, SW-регистрация
│   └── sw.js             # Service Worker (push + offline cache)
│
├── tests/                # 152 pytest-теста
│   ├── conftest.py       # Фикстуры (client, auth_client, SQLite test DB)
│   ├── test_auth.py
│   ├── test_projects.py
│   ├── test_vpk_audit.py
│   ├── test_tools.py     # Excel builders + шаблоны
│   ├── test_smr_kso.py   # Auth requirements
│   ├── test_security.py  # Magic bytes + CSRF
│   └── test_e2e_mobile.py # Playwright E2E (запуск: pytest -m e2e)
│
├── docs/
│   └── USER_GUIDE.md     # Руководство пользователя
│
├── .env.example          # Шаблон переменных окружения
├── pytest.ini            # Конфигурация тестов (E2E исключены по умолчанию)
├── requirements.txt
└── Procfile              # Railway: web + worker
```

---

## Безопасность

| Механизм | Реализация |
|---------|-----------|
| Хеширование паролей | PBKDF2-SHA256 (utils/passwords.py) |
| CSRF-защита | Токен в форме и в заголовке `X-CSRFToken` (middleware.py) |
| Rate limiting | 5 попыток/мин на вход, 20/мин на проверку телефона |
| Phone whitelist | Только номера из `/admin/users` могут войти |
| Session fixation | Новый session ID при каждом входе |
| Magic bytes | Валидация MIME по содержимому файла, не расширению |
| Security headers | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy` |
| Admin IP whitelist | `ADMIN_IP_WHITELIST` env var (опционально) |
| HTTPS | Автоматически через Railway |
| Sentry | Подключается через `SENTRY_DSN` (аккаунт создать на sentry.io) |
| Error monitoring | Email-алертинг через Brevo (1 письмо/мин макс.) |

---

## Поддержка

**Разработчик:** Месмер Денис  
**Email:** denis.mesmer@lenta.com  
**Версия:** 2.1.0 (июнь 2026)
