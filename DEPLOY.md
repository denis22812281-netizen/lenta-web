# Деплой на Railway.app

## 1. Подготовка репозитория GitHub

```bash
# В папке lenta-web создаём git-репозиторий
git init
git add .
git commit -m "Initial: Лента веб-система управления проектами"

# На github.com создай новый приватный репозиторий: lenta-web
# Затем:
git remote add origin https://github.com/ТВОЙ_ЛОГИН/lenta-web.git
git push -u origin main
```

## 2. Деплой на Railway

1. Открой railway.app → твой проект supportive-courage
2. Нажми **+ New Service** → **GitHub Repo**
3. Выбери репозиторий `lenta-web`
4. Railway автоматически определит Python и запустит `uvicorn main:app`

## 3. База данных (SQLite → Railway Volume)

Для сохранения данных при перезапуске:
1. В сервисе → **Settings** → **Volumes**
2. Добавь Volume: Mount Path = `/app/data`
3. В Variables добавь: `DATABASE_URL=sqlite:////app/data/lenta.db`

## 4. Переменные окружения (Variables)

| Переменная | Значение | Описание |
|------------|----------|----------|
| `SECRET_KEY` | случайная строка | Секрет для сессий |
| `ADMIN_LOGIN` | admin | Логин администратора |
| `ADMIN_PASSWORD` | СМЕНИТЬ! | Пароль |
| `GROQ_API_KEY` | gsk_... | Бесплатный ИИ (groq.com) |
| `DEEPSEEK_API_KEY` | sk-... | DeepSeek (дешёвый ИИ) |
| `PORT` | 8000 | Задаётся Railway автоматически |

## 5. Получить Groq API ключ (БЕСПЛАТНО)

1. Зайди на https://console.groq.com
2. Зарегистрируйся
3. API Keys → Create API Key
4. Скопируй ключ → вставь в Railway Variables

## 6. Проверка

После деплоя приложение будет доступно по URL вида:
`https://lenta-web-production-XXXX.up.railway.app`

Войти: `denis` / `denis2024`

## Безопасность входа

Реализовано:
- ✅ Логин + пароль (SHA-256)
- ✅ Сессионные куки (подписанные, 7 дней)
- ✅ HTTPS на Railway (автоматически)
- ✅ Разграничение ролей (admin / пользователь)

Дополнительно можно добавить:
- 2FA (двухфакторная аутентификация)
- OAuth через Microsoft/Google
- Белый список IP-адресов
