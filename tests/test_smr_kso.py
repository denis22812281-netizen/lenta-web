"""Tests for SMR and KSO AJAX endpoints: auth requirements and basic behaviour."""
import pytest

# ── SMR auth tests ─────────────────────────────────────────────────────────────

def test_smr_task_status_requires_auth(client):
    resp = client.post("/api/smr/task/9999/status", json={"status": "Выполнено"})
    assert resp.status_code == 401


def test_smr_task_emails_requires_auth(client):
    resp = client.post("/api/smr/task/9999/emails", json={"email1": "a@b.com"})
    assert resp.status_code == 401


def test_smr_send_confirm_requires_auth(client):
    resp = client.post("/api/smr/task/9999/send-confirm")
    assert resp.status_code == 401


def test_smr_send_report_requires_auth(client):
    resp = client.post("/api/smr/9999/send-report", json={"email": "a@b.com"})
    assert resp.status_code == 401


def test_smr_contacts_search_unauthenticated_returns_empty(client):
    resp = client.get("/api/smr/contacts?q=тест")
    assert resp.status_code == 200
    assert resp.json()["contacts"] == []


def test_smr_task_status_404_for_missing_task(auth_client):
    resp = auth_client.post("/api/smr/task/9999/status", json={"status": "Выполнено"})
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        assert "error" in resp.json()


def test_smr_send_report_404_for_missing_project(auth_client):
    resp = auth_client.post("/api/smr/9999/send-report", json={"email": "a@b.com"})
    assert resp.status_code in (200, 404)


# ── KSO auth tests ─────────────────────────────────────────────────────────────

def test_kso_toggle_requires_auth(client):
    resp = client.post("/kso/objects/9999/toggle")
    assert resp.status_code == 401


def test_kso_comment_requires_auth(client):
    resp = client.post("/api/kso/9999/comment", json={"comment": "test"})
    assert resp.status_code == 401


def test_kso_page_requires_login(client):
    resp = client.get("/kso", follow_redirects=False)
    assert resp.status_code in (302, 401)


# ── VPK AJAX auth tests ────────────────────────────────────────────────────────

def test_vpk_mark_read_requires_auth(client):
    resp = client.post("/vpk/reports/9999/read")
    assert resp.status_code == 401


def test_opening_upload_requires_auth(client):
    resp = client.post("/api/vpk/opening/upload-one", data={"project_id": "1"})
    assert resp.status_code == 401


def test_opening_feature_requires_auth(client):
    resp = client.post("/api/vpk/opening/9999/feature")
    assert resp.status_code == 401


def test_opening_delete_requires_auth(client):
    resp = client.post("/api/vpk/opening/9999/delete")
    assert resp.status_code == 401


def test_vpk_unread_unauthenticated_returns_empty(client):
    resp = client.get("/api/vpk/unread")
    assert resp.status_code == 200
    assert resp.json()["reports"] == []


def test_opening_photos_api_unauthenticated_returns_empty(client):
    resp = client.get("/api/vpk/opening/photos?project_id=1")
    assert resp.status_code == 200
    assert resp.json()["photos"] == []


# ── Admin AJAX auth tests ──────────────────────────────────────────────────────

def test_vpk_criteria_reorder_requires_admin(client):
    resp = client.post("/api/admin/vpk-criteria/reorder",
                       json=[{"id": 1, "order": 0}], follow_redirects=False)
    # require_admin → require_login → 302 to /login for unauthenticated users
    assert resp.status_code in (302, 401, 403)


def test_vpk_criteria_reorder_works_for_admin(auth_client):
    resp = auth_client.post("/api/admin/vpk-criteria/reorder", json=[])
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
