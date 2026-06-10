"""Тесты задач."""


def test_tasks_page(auth_client):
    r = auth_client.get("/tasks")
    assert r.status_code == 200


def test_create_task(auth_client):
    r = auth_client.post("/tasks/create", data={
        "title": "Тестовая задача",
        "description": "Описание",
        "priority": "Средний",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)

    # Задача создана
    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    t = db.query(models.Task).filter_by(title="Тестовая задача").first()
    assert t is not None
    tid = t.id
    db.close()

    # Удаляем
    auth_client.post(f"/tasks/{tid}/delete", follow_redirects=False)


def test_deadlines_page(auth_client):
    r = auth_client.get("/deadlines")
    assert r.status_code == 200


def test_api_tasks_json(auth_client):
    r = auth_client.get("/api/tasks")
    assert r.status_code == 200
    data = r.json()
    assert "tasks" in data
    assert "total" in data


def test_api_tasks_requires_auth(client):
    r = client.get("/api/tasks", follow_redirects=False)
    assert r.status_code == 401


def test_update_task_status(auth_client):
    r = auth_client.post("/tasks/create", data={
        "title": "Задача для статуса",
        "priority": "Высокий",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)

    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    t = db.query(models.Task).filter_by(title="Задача для статуса").first()
    assert t is not None
    tid = t.id
    db.close()

    r = auth_client.post(f"/tasks/{tid}/update-status", data={
        "status": "В работе",
        "completion_comment": "",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)

    db = TestingSessionLocal()
    t = db.query(models.Task).filter_by(id=tid).first()
    assert t.status == "В работе"
    db.close()


def test_deadlines_export(auth_client):
    r = auth_client.get("/deadlines/export")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
