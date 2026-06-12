"""Тесты: health endpoint, VPK precheck/submit авторизация, admin vpk-criteria, ZIP."""


# ── Health ──────────────────────────────────────────────────────────────────

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


def test_health_is_public(client):
    """Health endpoint не требует авторизации."""
    r = client.get("/health")
    assert r.status_code == 200


# ── VPK precheck — только авторизация ────────────────────────────────────────

def test_vpk_precheck_requires_auth(client):
    r = client.post("/vpk/precheck", data={}, follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("location", "")


def test_vpk_submit_requires_auth(client):
    r = client.post("/vpk/submit", data={}, follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("location", "")


def test_vpk_precheck_authenticated(auth_client):
    """Авторизованный пользователь получает форму (не 302)."""
    r = auth_client.post("/vpk/precheck", data={
        "project_id": "", "tk_text": "", "precheck_json": "{}",
    }, follow_redirects=False)
    # 200 (ошибка валидации) или 303 (redirect после сохранения) — не 302 на /login
    assert r.status_code != 302 or "/login" not in r.headers.get("location", "")


# ── Admin VPK criteria ────────────────────────────────────────────────────────

def test_vpk_criteria_requires_auth(client):
    r = client.get("/admin/vpk-criteria", follow_redirects=False)
    assert r.status_code == 302


def test_vpk_criteria_accessible_for_admin(auth_client):
    r = auth_client.get("/admin/vpk-criteria")
    assert r.status_code == 200
    assert "ВПК" in r.text


def test_vpk_criteria_add(auth_client):
    r = auth_client.post("/admin/vpk-criteria/add", data={
        "name": "Тестовый критерий pytest",
        "vpk_type": "1",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Тестовый критерий pytest" in r.text or "добавлен" in r.text.lower()


# ── Backup endpoint ───────────────────────────────────────────────────────────

def test_backup_requires_admin(client):
    r = client.get("/admin/backup", follow_redirects=False)
    assert r.status_code == 302


def test_backup_accessible_for_admin(auth_client):
    """В тестовом окружении pg_dump нет → 400 или 500, но не 302 и не 403."""
    r = auth_client.get("/admin/backup")
    assert r.status_code in (200, 400, 500)


# ── Opening gallery / ZIP (публичные) ────────────────────────────────────────

def test_opening_gallery_nonexistent_project(client):
    r = client.get("/opening/99999/gallery")
    assert r.status_code in (200, 404)


def test_opening_zip_nonexistent_project(client):
    r = client.get("/opening/99999/download-zip")
    assert r.status_code in (200, 404)


# ── Дашборд ───────────────────────────────────────────────────────────────────

def test_dashboard_authenticated(auth_client):
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "Лента" in r.text or "dashboard" in r.text.lower()


def test_dashboard_requires_auth(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
