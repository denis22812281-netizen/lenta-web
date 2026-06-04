# Техническая документация по развёртыванию
## Система управления строительными проектами «Лента.Проекты»

**Версия:** 1.0  
**Дата:** 02.06.2026  
**Ответственный:** Месмер Денис (+7 999 730 3914)

---

## 1. Требования к серверу

| Параметр | Минимум | Рекомендуется |
|---|---|---|
| ОС | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| CPU | 1 ядро | 2 ядра |
| RAM | 1 ГБ | 2 ГБ |
| Диск | 10 ГБ | 20 ГБ |
| Python | 3.11+ | 3.11+ |
| PostgreSQL | 14+ | 15+ |
| Nginx | 1.18+ | 1.24+ |

**Сетевые порты:**
- `80` — HTTP (перенаправление на HTTPS)
- `443` — HTTPS (основной)
- `5432` — PostgreSQL (только локально, не открывать наружу)
- `8000` — приложение (только локально, не открывать наружу)

---

## 2. Установка зависимостей

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Python и инструменты
sudo apt install -y python3.11 python3.11-venv python3-pip git nginx

# PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# (опционально) certbot для SSL-сертификата
sudo apt install -y certbot python3-certbot-nginx
```

---

## 3. Создание базы данных

```bash
sudo -u postgres psql

-- В консоли PostgreSQL:
CREATE USER lenta_user WITH PASSWORD 'замените_на_надёжный_пароль';
CREATE DATABASE lenta_db OWNER lenta_user;
GRANT ALL PRIVILEGES ON DATABASE lenta_db TO lenta_user;
\q
```

---

## 4. Развёртывание приложения

```bash
# Создаём системного пользователя для приложения
sudo useradd -m -s /bin/bash lenta

# Переключаемся на него
sudo su - lenta

# Клонируем репозиторий
git clone https://github.com/denis22812281-netizen/lenta-web.git /home/lenta/app
cd /home/lenta/app

# Создаём виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Переменные окружения

Создать файл `/home/lenta/app/.env`:

```bash
sudo nano /home/lenta/app/.env
```

Содержимое файла:

```env
# ── ОБЯЗАТЕЛЬНЫЕ ──────────────────────────────────────────────────────────────

# Секретный ключ сессий (сгенерировать: python3 -c "import secrets; print(secrets.token_hex(32))")
SECRET_KEY=вставить_сгенерированный_ключ_64_символа

# Подключение к базе данных
DATABASE_URL=postgresql://lenta_user:пароль@localhost:5432/lenta_db

# Телефон первого администратора (в формате +7XXXXXXXXXX)
ADMIN_PHONE=+79997303914
ADMIN_NAME=Месмер Денис

# Признак production-среды (включает Secure cookie)
RAILWAY_ENVIRONMENT=production

# ── EMAIL-УВЕДОМЛЕНИЯ (опционально) ───────────────────────────────────────────
# Если не задать — уведомления не отправляются, всё остальное работает

# API-ключ сервиса Brevo (sendinblue.com) ИЛИ настроить SMTP ниже
BREVO_API_KEY=

# ── ИИ-АССИСТЕНТ (опционально, можно не заполнять) ────────────────────────────
# Если не задать — раздел ИИ недоступен, всё остальное работает нормально

GROQ_API_KEY=
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=

# ── МОНИТОРИНГ ОШИБОК (опционально) ───────────────────────────────────────────
SENTRY_DSN=

# ── ХРАНИЛИЩЕ ФОТО (опционально) ──────────────────────────────────────────────
# Если не задать — фото хранятся локально на сервере
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=

# ── URL ПРИЛОЖЕНИЯ ────────────────────────────────────────────────────────────
APP_URL=https://projects.lenta.com
```

Установить права доступа к файлу:

```bash
chmod 600 /home/lenta/app/.env
```

---

## 6. Настройка автозапуска (systemd)

Создать файл сервиса:

```bash
sudo nano /etc/systemd/system/lenta-web.service
```

Содержимое:

```ini
[Unit]
Description=Лента.Проекты — система управления строительными проектами
After=network.target postgresql.service

[Service]
User=lenta
Group=lenta
WorkingDirectory=/home/lenta/app
Environment="PATH=/home/lenta/app/venv/bin"
EnvironmentFile=/home/lenta/app/.env
ExecStart=/home/lenta/app/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Включить и запустить:

```bash
sudo systemctl daemon-reload
sudo systemctl enable lenta-web
sudo systemctl start lenta-web

# Проверить статус
sudo systemctl status lenta-web
```

---

## 7. Настройка Nginx

```bash
sudo nano /etc/nginx/sites-available/lenta-web
```

Содержимое:

```nginx
server {
    listen 80;
    server_name projects.lenta.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name projects.lenta.com;

    # SSL-сертификат (корпоративный или Let's Encrypt)
    ssl_certificate     /etc/ssl/lenta/cert.pem;
    ssl_certificate_key /etc/ssl/lenta/key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # Ограничение размера загружаемых файлов
    client_max_body_size 55M;

    # Статические файлы раздаёт nginx напрямую (быстрее)
    location /static/ {
        alias /home/lenta/app/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Всё остальное — проксируется в приложение
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Активировать конфигурацию:

```bash
sudo ln -s /etc/nginx/sites-available/lenta-web /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8. Резервное копирование базы данных

Создать скрипт backup:

```bash
sudo nano /home/lenta/backup.sh
```

Содержимое:

```bash
#!/bin/bash
BACKUP_DIR="/backup/lenta"
DATE=$(date +%Y-%m-%d_%H-%M)
mkdir -p $BACKUP_DIR

pg_dump -U lenta_user -h localhost lenta_db \
    | gzip > $BACKUP_DIR/lenta_db_$DATE.sql.gz

# Удаляем бэкапы старше 30 дней
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

echo "Backup completed: lenta_db_$DATE.sql.gz"
```

```bash
chmod +x /home/lenta/backup.sh

# Добавить в cron — запуск каждую ночь в 02:00
sudo crontab -e
# Добавить строку:
# 0 2 * * * /home/lenta/backup.sh >> /var/log/lenta-backup.log 2>&1
```

---

## 9. Обновление приложения

```bash
sudo su - lenta
cd /home/lenta/app

# Получить обновления из репозитория
git pull origin main

# Обновить зависимости (если изменился requirements.txt)
source venv/bin/activate
pip install -r requirements.txt

# Перезапустить сервис
sudo systemctl restart lenta-web

# Проверить что всё запустилось
sudo systemctl status lenta-web
sudo journalctl -u lenta-web -n 50
```

---

## 10. Восстановление из резервной копии

```bash
# Остановить приложение
sudo systemctl stop lenta-web

# Восстановить БД из бэкапа
gunzip -c /backup/lenta/lenta_db_2026-06-01_02-00.sql.gz \
    | psql -U lenta_user -h localhost lenta_db

# Запустить приложение
sudo systemctl start lenta-web
```

---

## 11. Проверка работоспособности

```bash
# Статус сервиса
sudo systemctl status lenta-web

# Логи приложения (последние 100 строк)
sudo journalctl -u lenta-web -n 100

# Проверка доступности
curl -I http://localhost:8000

# Статус nginx
sudo systemctl status nginx
sudo nginx -t
```

---

## 12. Контактное лицо

По всем вопросам, связанным с приложением:

**Месмер Денис**  
Менеджер проектов, отдел реконструкции и строительства  
Телефон: +7 999 730 3914  
Email: denis.mesmer@lenta.com
