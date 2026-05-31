# Инструкция по развёртыванию — Лента.PM

Полное руководство для IT-администратора по установке на корпоративный сервер.

---

## Требования к серверу

| Компонент | Минимум | Рекомендуется |
|-----------|---------|--------------|
| ОС | Ubuntu 20.04 / CentOS 8 | Ubuntu 22.04 LTS |
| CPU | 2 ядра | 4 ядра |
| RAM | 2 ГБ | 4 ГБ |
| Диск | 20 ГБ | 50 ГБ |
| Python | 3.11+ | 3.12 |
| PostgreSQL | 14+ | 16 |

---

## Шаг 1 — Установка системных пакетов

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip \
    postgresql postgresql-contrib nginx certbot python3-certbot-nginx git
```

---

## Шаг 2 — База данных

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE lenta_pm;
CREATE USER lenta_user WITH PASSWORD 'надёжный_пароль';
GRANT ALL PRIVILEGES ON DATABASE lenta_pm TO lenta_user;
\q
```

---

## Шаг 3 — Загрузка кода

```bash
sudo mkdir -p /opt/lenta-pm
sudo chown $USER:$USER /opt/lenta-pm
cd /opt/lenta-pm
unzip lenta-pm-v1.0.zip
```

---

## Шаг 4 — Виртуальное окружение

```bash
cd /opt/lenta-pm
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Шаг 5 — Переменные окружения

```bash
cp .env.example .env
nano .env
```

Заполнить обязательно:
- SECRET_KEY — сгенерировать: `python -c "import secrets; print(secrets.token_hex(32))"`
- DATABASE_URL — строка подключения PostgreSQL
- ADMIN_PHONE — телефон первого администратора +7XXXXXXXXXX
- APP_DOMAIN — домен сервера (например lenta-pm.lenta.ru)

---

## Шаг 6 — Проверочный запуск

```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

Открыть http://IP-сервера:8000 — если страница открылась, нажать Ctrl+C.

---

## Шаг 7 — Автозапуск (systemd)

```bash
sudo nano /etc/systemd/system/lenta-pm.service
```

```ini
[Unit]
Description=Лента.PM
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/lenta-pm
EnvironmentFile=/opt/lenta-pm/.env
ExecStart=/opt/lenta-pm/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable lenta-pm
sudo systemctl start lenta-pm
sudo systemctl status lenta-pm
```

---

## Шаг 8 — Nginx

```bash
sudo nano /etc/nginx/sites-available/lenta-pm
```

```nginx
server {
    listen 80;
    server_name lenta-pm.ваш-домен.ru;
    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /opt/lenta-pm/static;
        expires 7d;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/lenta-pm /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Шаг 9 — SSL (HTTPS)

```bash
sudo certbot --nginx -d lenta-pm.ваш-домен.ru
```

---

## Шаг 10 — Первый вход

1. Открыть https://lenta-pm.ваш-домен.ru
2. Ввести телефон из ADMIN_PHONE
3. Создать пароль
4. Открыть /admin/users → добавить пользователей

---

## Резервное копирование

```bash
sudo nano /opt/lenta-pm/backup.sh
```

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M)
BACKUP_DIR=/opt/lenta-pm/backups
mkdir -p $BACKUP_DIR
pg_dump -U lenta_user lenta_pm > $BACKUP_DIR/db_$DATE.sql
tar -czf $BACKUP_DIR/files_$DATE.tar.gz /opt/lenta-pm/static/uploads
find $BACKUP_DIR -mtime +30 -delete
echo "Бэкап выполнен: $DATE"
```

```bash
chmod +x /opt/lenta-pm/backup.sh
crontab -e
# Добавить: 0 3 * * * /opt/lenta-pm/backup.sh
```

---

## Обновление

```bash
sudo systemctl stop lenta-pm
/opt/lenta-pm/backup.sh
# Распаковать новый архив
source /opt/lenta-pm/venv/bin/activate
pip install -r /opt/lenta-pm/requirements.txt
sudo systemctl start lenta-pm
```

---

## Диагностика

```bash
sudo journalctl -u lenta-pm -f          # логи приложения
sudo tail -f /var/log/nginx/error.log   # логи nginx
sudo systemctl restart lenta-pm         # перезапуск
```

---

## Техническая поддержка

Разработчик: Месмер Денис
Email: denis22812281@gmail.com
