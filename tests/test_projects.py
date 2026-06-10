"""Тесты работы с проектами."""


def test_dashboard_authenticated(auth_client):
    r = auth_client.get("/")
    assert r.status_code == 200


def test_projects_page_authenticated(auth_client):
    r = auth_client.get("/projects")
    assert r.status_code == 200


def test_create_and_delete_project(auth_client):
    # Создаём проект
    r = auth_client.post("/projects/create", data={
        "name": "Тест ТК 999",
        "tk_number": "999",
        "city": "Москва",
        "project_type": "Констракшн",
        "status": "Активный",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)

    # Проверяем что появился в списке
    r = auth_client.get("/projects")
    assert "999" in r.text

    # Получаем id из БД
    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    p = db.query(models.Project).filter_by(tk_number="999").first()
    assert p is not None
    pid = p.id
    db.close()

    # Удаляем
    r = auth_client.post(f"/projects/{pid}/delete", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_reconstruct_page(auth_client):
    r = auth_client.get("/reconstruct")
    assert r.status_code == 200


def test_construction_page(auth_client):
    r = auth_client.get("/construction")
    assert r.status_code == 200


def test_excel_import_too_large(auth_client):
    from urllib.parse import unquote
    big_file = b"X" * (11 * 1024 * 1024)  # 11 MB
    r = auth_client.post(
        "/import-reconstruct",
        files={"file": ("big.xlsx", big_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    location = unquote(r.headers.get("location", ""))
    assert "большой" in location


# ─── Новые тесты безопасности ─────────────────────────────────────────────────

def test_export_excel_requires_auth(client):
    """Экспорт проектов должен требовать авторизацию."""
    r = client.get("/api/export/projects-excel", follow_redirects=False)
    assert r.status_code == 302


def test_export_excel_returns_xlsx_when_authed(auth_client):
    """Авторизованный пользователь получает xlsx-файл."""
    r = auth_client.get("/api/export/projects-excel")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_bulk_update_rejects_invalid_status(auth_client):
    """bulk-update должен отклонять произвольные строки статуса."""
    r = auth_client.post("/api/projects/bulk-update",
                         json={"ids": [], "action": "status:ХАКЕР"})
    assert r.status_code == 400
    data = r.json()
    assert data["ok"] is False


def test_bulk_update_accepts_valid_status(auth_client):
    """bulk-update принимает статус из списка STATUSES (создаём проект для теста)."""
    from tests.conftest import TestingSessionLocal
    import models

    # Создаём временный проект
    auth_client.post("/projects/create", data={
        "name": "Тест bulk-update", "tk_number": "BULK1", "city": "Москва",
        "project_type": "Констракшн", "status": "Планирование",
    }, follow_redirects=False)

    db = TestingSessionLocal()
    p = db.query(models.Project).filter_by(tk_number="BULK1").first()
    pid = p.id if p else None
    db.close()

    if pid:
        r = auth_client.post("/api/projects/bulk-update",
                             json={"ids": [pid], "action": "status:Активный"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Убираем за собой
        auth_client.post(f"/projects/{pid}/delete", follow_redirects=False)


def test_project_detail_404_for_unknown(auth_client):
    r = auth_client.get("/projects/99999")
    assert r.status_code == 404
