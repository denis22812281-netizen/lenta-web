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
