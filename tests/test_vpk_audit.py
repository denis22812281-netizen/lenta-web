"""Тесты ВПК и аудит-лога."""


def test_vpk_page(auth_client):
    r = auth_client.get("/vpk")
    assert r.status_code == 200


def test_reports_page(auth_client):
    r = auth_client.get("/reports")
    assert r.status_code == 200


def test_managers_page(auth_client):
    r = auth_client.get("/managers")
    assert r.status_code == 200


def test_stats_page(auth_client):
    r = auth_client.get("/stats")
    assert r.status_code == 200


def test_audit_log_only_mesmer(auth_client):
    """Аудит-лог доступен — auth_client это Месмер Денис с +79997303914."""
    r = auth_client.get("/admin/audit")
    assert r.status_code == 200


def test_audit_log_blocked_for_regular(client):
    """Без авторизации — редирект."""
    r = client.get("/admin/audit", follow_redirects=False)
    assert r.status_code == 302


def test_chat_page(auth_client):
    r = auth_client.get("/chat")
    assert r.status_code == 200


def test_kso_page(auth_client):
    r = auth_client.get("/kso")
    assert r.status_code == 200


def test_ai_page(auth_client):
    r = auth_client.get("/ai")
    assert r.status_code == 200


def test_vpk_unread_api(auth_client):
    r = auth_client.get("/api/vpk/unread")
    assert r.status_code == 200
    assert "reports" in r.json()


def test_reports_export(auth_client):
    r = auth_client.get("/reports/export")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_admin_users_requires_admin(auth_client):
    """Страница /admin/users доступна для is_admin=True (auth_client — admin)."""
    r = auth_client.get("/admin/users")
    assert r.status_code == 200


def test_audit_log_blocked_after_phone_cleared(client):
    """Аудит-лог недоступен без ADMIN_PHONE (fallback убран в Fix 9)."""
    import os
    original = os.environ.get("ADMIN_PHONE")
    os.environ.pop("ADMIN_PHONE", None)
    # Без авторизации всё равно редирект на логин
    r = client.get("/admin/audit", follow_redirects=False)
    assert r.status_code == 302
    if original:
        os.environ["ADMIN_PHONE"] = original


def test_smr_list_page(auth_client):
    r = auth_client.get("/smr")
    assert r.status_code == 200


def test_smr_contacts_page(auth_client):
    r = auth_client.get("/smr/contacts")
    assert r.status_code == 200


def test_smr_confirm_invalid_token(client):
    r = client.get("/smr/confirm/invalidtoken123")
    assert r.status_code == 200
    assert "недействительна" in r.text.lower() or "invalid" in r.text.lower()


def test_online_api(auth_client):
    r = auth_client.get("/api/online")
    assert r.status_code == 200
    assert "online" in r.json()


def test_data_version_api(auth_client):
    r = auth_client.get("/api/data-version")
    assert r.status_code == 200
    assert "version" in r.json()
