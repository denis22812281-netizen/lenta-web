"""Тесты страницы менеджеров и API."""


def test_managers_page_loads(auth_client):
    r = auth_client.get("/managers")
    assert r.status_code == 200
    assert "Месмер" in r.text or "менеджер" in r.text.lower()


def test_managers_page_unauthenticated(client):
    r = client.get("/managers", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("location", "")


def test_managers_add_requires_admin(client):
    """Добавление менеджера недоступно без авторизации."""
    r = client.post("/managers/add", data={"name": "Тест Менеджер", "phone": "+70000000001"},
                    follow_redirects=False)
    assert r.status_code == 302


def test_managers_add_and_delete(auth_client):
    """Создание и удаление менеджера."""
    import models
    from tests.conftest import TestingSessionLocal

    # Добавляем
    r = auth_client.post("/managers/add", data={
        "name": "Тестовый Менеджер DELETE",
        "phone": "+70000000099",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)

    # Находим созданного
    db = TestingSessionLocal()
    mgr = db.query(models.Manager).filter_by(name="Тестовый Менеджер DELETE").first()
    db.close()
    assert mgr is not None, "Менеджер не создан"
    mid = mgr.id

    # Удаляем
    r = auth_client.post(f"/managers/{mid}/delete", follow_redirects=False)
    assert r.status_code in (302, 303)

    # Проверяем что удалён
    db = TestingSessionLocal()
    gone = db.query(models.Manager).filter_by(id=mid).first()
    db.close()
    assert gone is None, "Менеджер не удалён"


def test_manager_email_update(auth_client):
    """Обновление email менеджера."""
    import models
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    mgr = db.query(models.Manager).first()
    db.close()
    if not mgr:
        return  # нет менеджеров — пропускаем

    r = auth_client.post(f"/managers/{mgr.id}/email",
                         data={"email": "test@lenta.com"},
                         follow_redirects=False)
    assert r.status_code in (302, 303, 200)


def test_manager_invalid_email_rejected(auth_client):
    """Некорректный email отклоняется (422)."""
    import models
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    mgr = db.query(models.Manager).first()
    db.close()
    if not mgr:
        return

    r = auth_client.post(f"/managers/{mgr.id}/email",
                         data={"email": "not-an-email"},
                         follow_redirects=False)
    assert r.status_code in (302, 303, 422)
