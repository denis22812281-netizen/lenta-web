"""Тесты авторизации."""


def test_login_page_loads(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "Лента" in r.text or "login" in r.text.lower()


def test_unauthenticated_dashboard_redirects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["location"]


def test_unauthenticated_projects_redirects(client):
    r = client.get("/projects", follow_redirects=False)
    assert r.status_code == 302


def test_unauthenticated_tasks_redirects(client):
    r = client.get("/tasks", follow_redirects=False)
    assert r.status_code == 302


def test_unauthenticated_vpk_redirects(client):
    r = client.get("/vpk", follow_redirects=False)
    assert r.status_code == 302


def test_unauthenticated_managers_redirects(client):
    r = client.get("/managers", follow_redirects=False)
    assert r.status_code == 302


def test_check_phone_unknown_number(client):
    r = client.post("/login/check-phone", data={"phone": "+70000000000"})
    assert r.status_code == 200
    assert "не авторизован" in r.text.lower() or "закрыт" in r.text.lower()


def test_qr_page_loads(client):
    r = client.get("/qr")
    assert r.status_code == 200


def test_wrong_password_rejected(client):
    """Неверный пароль не пропускает в систему."""
    import models
    import utils.passwords as pw
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    phone = "+79001112233"
    if not db.query(models.PhoneWhitelist).filter_by(phone=phone).first():
        db.add(models.PhoneWhitelist(phone=phone, display_name="Тест Тестов", is_admin=False))
        db.commit()
    if not db.query(models.User).filter_by(phone=phone).first():
        db.add(models.User(
            phone=phone, username=phone,
            password_hash=pw.hash_password("correct_pass"),
            display_name="Тест Тестов",
        ))
        db.commit()
    db.close()

    client.post("/login/check-phone", data={"phone": phone})
    r = client.post("/login/enter", data={"phone": phone, "password": "wrong_pass"},
                    follow_redirects=False)
    assert r.status_code in (200, 302)
    if r.status_code == 302:
        assert "/login" in r.headers.get("location", "")
    else:
        assert "неверн" in r.text.lower() or "пароль" in r.text.lower() or "ошибка" in r.text.lower()


def test_logout(auth_client):
    """После logout защищённые страницы недоступны."""
    from fastapi.testclient import TestClient

    from database import get_db
    from main import app
    from tests.conftest import override_get_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        import models
        import utils.passwords as pw
        from tests.conftest import TestingSessionLocal
        db = TestingSessionLocal()
        phone = "+79009876543"
        if not db.query(models.PhoneWhitelist).filter_by(phone=phone).first():
            db.add(models.PhoneWhitelist(phone=phone, display_name="Logout Test", is_admin=False))
            db.commit()
        if not db.query(models.User).filter_by(phone=phone).first():
            db.add(models.User(
                phone=phone, username=phone,
                password_hash=pw.hash_password("pass1234"),
                display_name="Logout Test",
            ))
            db.commit()
        db.close()

        c.post("/login/check-phone", data={"phone": phone})
        c.post("/login/enter", data={"phone": phone, "password": "pass1234"})
        r_before = c.get("/projects", follow_redirects=False)
        assert r_before.status_code == 200

        c.get("/logout")
        r_after = c.get("/projects", follow_redirects=False)
        assert r_after.status_code == 302
