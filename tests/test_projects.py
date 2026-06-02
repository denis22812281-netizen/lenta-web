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
    big_file = b"X" * (11 * 1024 * 1024)  # 11 MB
    r = auth_client.post(
        "/import-reconstruct",
        files={"file": ("big.xlsx", big_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert "большой" in r.headers.get("location", "")
