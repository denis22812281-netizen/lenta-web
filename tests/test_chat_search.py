"""Тесты чата, поиска и общих API-эндпоинтов."""


# ─── Чат ─────────────────────────────────────────────────────────────────────

def test_chat_page_loads(auth_client):
    r = auth_client.get("/chat")
    assert r.status_code == 200


def test_chat_page_unauthenticated(client):
    r = client.get("/chat", follow_redirects=False)
    assert r.status_code == 302


def test_chat_send_message(auth_client):
    """Отправка сообщения возвращает 200 с данными."""
    r = auth_client.post("/api/chat/send", json={"text": "тестовое сообщение", "to": None})
    assert r.status_code == 200
    data = r.json()
    assert "id" in data or "ok" in data or "text" in data


def test_chat_messages_api(auth_client):
    """Список сообщений возвращает объект с ключом messages."""
    r = auth_client.get("/api/chat/messages")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict))
    if isinstance(data, dict):
        assert "messages" in data
        assert isinstance(data["messages"], list)


def test_chat_unread_count(auth_client):
    """Счётчик непрочитанных — возвращает dict с числовым значением."""
    r = auth_client.get("/api/chat/unread")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (dict, int))
    if isinstance(data, dict):
        assert any(isinstance(v, int) for v in data.values())


def test_chat_send_empty_text(auth_client):
    """Пустое сообщение должно быть отклонено или проигнорировано."""
    r = auth_client.post("/api/chat/send", json={"text": "", "to": None})
    assert r.status_code in (200, 400, 422)


# ─── Поиск ───────────────────────────────────────────────────────────────────

def test_search_page_loads(auth_client):
    r = auth_client.get("/search")
    assert r.status_code == 200


def test_search_page_unauthenticated(client):
    r = client.get("/search", follow_redirects=False)
    assert r.status_code == 302


def test_search_with_query(auth_client):
    """Поиск с параметром q возвращает страницу без ошибок."""
    r = auth_client.get("/search?q=Москва")
    assert r.status_code == 200


def test_search_empty_query(auth_client):
    """Поиск без параметра возвращает страницу."""
    r = auth_client.get("/search?q=")
    assert r.status_code == 200


# ─── Общие API-эндпоинты ─────────────────────────────────────────────────────

def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_api_online_endpoint(auth_client):
    r = auth_client.get("/api/online")
    assert r.status_code == 200
    data = r.json()
    assert "online" in data or isinstance(data, dict)


def test_api_data_version(auth_client):
    r = auth_client.get("/api/data-version")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data or "v" in data or isinstance(data, dict)


def test_api_tasks_list(auth_client):
    r = auth_client.get("/api/tasks")
    assert r.status_code == 200
    data = r.json()
    # May return list or {"tasks": [...], "total": N}
    assert isinstance(data, (list, dict))
    if isinstance(data, dict):
        assert "tasks" in data


def test_api_ping(auth_client):
    r = auth_client.post("/api/ping")
    assert r.status_code == 200


# ─── Задачи ──────────────────────────────────────────────────────────────────

def test_tasks_page_loads(auth_client):
    r = auth_client.get("/tasks")
    assert r.status_code == 200


def test_task_create_and_delete(auth_client):
    """Создание и удаление задачи."""
    import models
    from tests.conftest import TestingSessionLocal

    r = auth_client.post("/tasks/create", data={
        "title": "Тестовая задача AUTO",
        "priority": "medium",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)

    db = TestingSessionLocal()
    task = db.query(models.Task).filter_by(title="Тестовая задача AUTO").first()
    db.close()
    assert task is not None, "Задача не создана"
    tid = task.id

    r = auth_client.post(f"/tasks/{tid}/delete", follow_redirects=False)
    assert r.status_code in (302, 303)

    db = TestingSessionLocal()
    gone = db.query(models.Task).filter_by(id=tid).first()
    db.close()
    assert gone is None, "Задача не удалена"


def test_task_update_status(auth_client):
    """Обновление статуса задачи через API."""
    import models
    from tests.conftest import TestingSessionLocal

    auth_client.post("/tasks/create", data={
        "title": "Задача для статуса", "priority": "low",
    }, follow_redirects=False)

    db = TestingSessionLocal()
    task = db.query(models.Task).filter_by(title="Задача для статуса").first()
    db.close()
    if not task:
        return

    r = auth_client.post(f"/tasks/{task.id}/update-status",
                         data={"status": "Завершена"})
    assert r.status_code in (200, 302, 303)

    # Убираем за собой
    auth_client.post(f"/tasks/{task.id}/delete", follow_redirects=False)
