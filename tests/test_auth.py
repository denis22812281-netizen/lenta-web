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
