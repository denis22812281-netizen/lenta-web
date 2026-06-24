"""Тесты страниц дедлайнов и уведомлений."""


def test_deadlines_check_api(auth_client):
    """/api/deadlines/check возвращает JSON с нужными ключами."""
    r = auth_client.get("/api/deadlines/check")
    assert r.status_code == 200
    data = r.json()
    assert "urgent_tasks" in data
    assert "overdue_tasks" in data
    assert "urgent_projects" in data
    assert isinstance(data["urgent_tasks"], list)
    assert isinstance(data["overdue_tasks"], list)
    assert isinstance(data["urgent_projects"], list)


def test_deadlines_check_unauthenticated(client):
    """Неавторизованный получает пустые списки (не 302)."""
    r = client.get("/api/deadlines/check")
    assert r.status_code == 200
    data = r.json()
    assert data["urgent_tasks"] == []
    assert data["overdue_tasks"] == []
    assert data["urgent_projects"] == []


def test_construction_notifications_api(auth_client):
    """/api/notifications/construction возвращает список уведомлений."""
    r = auth_client.get("/api/notifications/construction")
    assert r.status_code == 200
    data = r.json()
    assert "notifications" in data
    assert isinstance(data["notifications"], list)


def test_reconstruct_notifications_api(auth_client):
    """/api/notifications/reconstruct возвращает список уведомлений."""
    r = auth_client.get("/api/notifications/reconstruct")
    assert r.status_code == 200
    data = r.json()
    assert "notifications" in data
    assert isinstance(data["notifications"], list)


def test_reconstruct_page_loads(auth_client):
    """Страница реконструкции доступна."""
    r = auth_client.get("/reconstruct")
    assert r.status_code == 200


def test_construction_page_loads(auth_client):
    """Страница констракшн доступна."""
    r = auth_client.get("/construction")
    assert r.status_code == 200


def test_deadlines_with_overdue_project(auth_client):
    """Просроченный проект попадает в urgent_projects если тип Констракшн."""
    from datetime import date, timedelta

    import models
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    p = models.Project(
        name="Тест просроченный", tk_number="OVERDUE_TEST",
        city="Тест", project_type="Констракшн",
        status="Активный",
        end_date=date.today() + timedelta(days=3),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    pid = p.id
    db.close()

    r = auth_client.get("/api/deadlines/check")
    assert r.status_code == 200
    data = r.json()
    ids_found = [pp["id"] for pp in data["urgent_projects"]]
    assert pid in ids_found

    db = TestingSessionLocal()
    db.query(models.Project).filter_by(id=pid).delete()
    db.commit()
    db.close()
