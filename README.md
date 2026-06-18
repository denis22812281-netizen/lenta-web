# Лента.PM — Система управления проектами

Внутренняя операционная система для дирекции строительства ЛЕНТА.  
Управляет открытиями магазинов, реконструкциями, задачами, ВПК-отчётами и командой из ~10 менеджеров.

---

## Возможности

| Модуль | Функции |
|--------|---------|
| **Проекты** | Реконструкции и констракшн: статусы, этапы, дедлайны, история, вложения, экспорт Excel |
| **Gantt** | Интерактивная диаграмма Ганта с drag-and-drop (frappe-gantt) |
| **Задачи** | Постановка с приоритетами, исполнителями, фото-отчётами |
| **ВПК-отчёты** | Чеклисты ВПК-1 и ВПК-2 с фото, экспорт в Excel, учёт прочтения |
| **Адаптационные карточки** | Цифровые анкеты на основе XLSX-шаблона + фото объекта |
| **График СМР** | Временная шкала с вехами, email-подтверждения, push-уведомления |
| **Чат** | Личные и общий чат с фото, онлайн-статусы, push-уведомления |
| **ИИ-ассистент** | Claude / Groq / DeepSeek с контекстом проектов |
| **Аналитика** | Дашборд открытий, просрочки, статистика по менеджерам |
| **Дедлайны** | Единый экран всех сроков по проектам и задачам |
| **КСО** | Объекты соцответственности, готовность, графики |
| **PWA** | Устанавливается как приложение, работает offline, push-уведомления |

---

## Технологии

- **Backend:** Python 3.11 / FastAPI 0.115 / SQLAlchemy 2.0
- **Frontend:** Jinja2 + Bootstrap 5.3 dark theme + Vanilla JS
- **БД:** PostgreSQL (production) / SQLite (локальная разработка)
- **Хранилище фото:** Cloudinary (auto-quality, auto-format)
- **Email:** Brevo (SMTP)
- **Push:** Web Push API / VAPID / pywebpush
- **Деплой:** Railway.app (NIXPACKS, auto-deploy)
- **CI/CD:** GitHub Actions (тесты + `railway up` на merge в main)
- **Тесты:** pytest + pytest-asyncio (84 тестов)

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
SECRET_KEY=local-dev-key-change-me
DATABASE_URL=sqlite:///./lenta.db
ADMIN_PHONE=+79997303914

# 5. Запуск
uvicorn main:app --reload

# Открыть: http://localhost:8000
```

Войти с номером `+79997303914` → создать пароль при первом входе.

---

## Тесты

```bash
pytest tests/ -v            # все 84 теста
pytest tests/test_auth.py   # отдельный модуль
```

Тесты используют SQLite — PostgreSQL не нужен. `TESTING=1` отключает CSRF.

---

## Деплой на Railway

### Новый деплой

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### Переменные окружения (обязательные)

```
SECRET_KEY=<random 64 hex chars>
DATABASE_URL=<railway postgres url>
ADMIN_PHONE=+7XXXXXXXXXX
APP_DOMAIN=<your-app>.up.railway.app
APP_URL=https://<your-app>.up.railway.app
```

### CI/CD автодеплой

В GitHub → Settings → Secrets добавить `RAILWAY_TOKEN` (из Railway Dashboard → Account → Tokens).  
После этого каждый push в `main` → тесты → автодеплой.

---

## Добавить пользователя

1. Войти как администратор
2. Перейти в `/admin/users`
3. Нажать «Добавить» → ввести номер телефона `+7XXXXXXXXXX`
4. Пользователь при первом входе создаёт пароль самостоятельно

---

## Структура проекта

```
lenta-web/
├── main.py               Точка входа, middleware, роутеры, startup
├── deps.py               Shared зависимости (auth, templates, limiter)
├── database.py           SQLAlchemy engine, get_db, db_session
├── config.py             Константы (типы проектов, статусы, команда)
├── migrations.py         Идемпотентные миграции схемы БД
├── worker.py             Standalone worker (backup + push, APScheduler)
├── models/               SQLAlchemy модели (33 класса в 8 файлах)
├── routes/               25 FastAPI роутеров
├── services/             Бизнес-логика
│   ├── background.py     3 async loop (sync, smr, digest)
│   ├── push_service.py   Web Push / VAPID
│   ├── backup.py         PostgreSQL backup
│   ├── cloud_storage.py  Cloudinary
│   ├── email_service.py  Brevo SMTP
│   └── excel_import.py   Парсинг Excel → Project
├── templates/            39 Jinja2 шаблонов
├── static/
│   ├── css/style.css     900+ строк кастомного CSS
│   ├── js/app.js         Клиентская логика (toast, theme, deadlines)
│   └── sw.js             Service Worker (push + offline cache)
└── tests/                84 pytest теста
```

---

## Безопасность

| Механизм | Статус |
|---------|--------|
| Хеширование паролей | PBKDF2-SHA256 + Argon2 fallback |
| CSRF-токены | Все POST-формы |
| 2FA TOTP | Google Authenticator |
| WebAuthn | Face ID / Touch ID (passkeys) |
| Rate limiting | 5/мин login, 20/мин phone check |
| IP whitelist | `/admin/*` только из разрешённых IP |
| Audit log | Все действия авторизованных пользователей |
| Phone whitelist | Только добавленные номера могут войти |
| Session version | Инвалидация сессий после смены пароля |
| CSP / Security headers | X-Frame-Options DENY, nosniff, Referrer-Policy |
| HTTPS | Автоматически через Railway |

---

## Поддержка

**Разработчик:** Месмер Денис  
**Email:** denis.mesmer@lenta.com  
**Версия:** 2.0.0 (июнь 2026)
