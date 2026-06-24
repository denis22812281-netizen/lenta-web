"""Unit-тесты для карточек адаптации."""
import pytest

# ── helpers ──────────────────────────────────────────────────────────────────

def _login(client):
    """Создаёт пользователя и логинится (без 2FA)."""
    import models
    import utils.passwords as pw
    from tests.conftest import TestingSessionLocal
    db = TestingSessionLocal()
    phone = "+79990000001"
    if not db.query(models.PhoneWhitelist).filter_by(phone=phone).first():
        db.add(models.PhoneWhitelist(phone=phone, display_name="Тестовый Пользователь", is_admin=True))
        db.commit()
    if not db.query(models.User).filter_by(phone=phone).first():
        db.add(models.User(
            phone=phone, username=phone,
            password_hash=pw.hash_password("test1234"),
            display_name="Тестовый Пользователь", is_admin=True,
        ))
        db.commit()
    db.close()
    client.post("/login/check-phone", data={"phone": phone})
    client.post("/login/enter", data={"phone": phone, "password": "test1234"})
    return phone


# ── tests ─────────────────────────────────────────────────────────────────────

class TestAdaptationList:
    def test_redirect_if_not_logged_in(self, client):
        r = client.get("/adaptation", follow_redirects=False)
        assert r.status_code in (302, 303)

    def test_list_visible_after_login(self, client):
        _login(client)
        r = client.get("/adaptation")
        assert r.status_code == 200
        assert "Карточки адаптации" in r.text or "адаптации" in r.text.lower()

    def test_new_form_visible(self, client):
        _login(client)
        r = client.get("/adaptation/new")
        assert r.status_code == 200
        assert "tk_number" in r.text


class TestAdaptationCreate:
    def _csrf(self, client):
        _login(client)
        r = client.get("/adaptation/new")
        import re
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
        return m.group(1) if m else ""

    def test_create_card(self, client):
        token = self._csrf(client)
        r = client.post("/adaptation/save", data={
            "tk_number": "TEST-001",
            "csrf_token": token,
        }, follow_redirects=False)
        assert r.status_code in (302, 303)
        assert "/adaptation/" in r.headers.get("location", "")

    def test_created_card_appears_in_list(self, client):
        token = self._csrf(client)
        client.post("/adaptation/save", data={
            "tk_number": "TEST-LIST",
            "csrf_token": token,
        })
        r = client.get("/adaptation")
        assert "TEST-LIST" in r.text

    def test_edit_existing_card(self, client):
        token = self._csrf(client)
        r = client.post("/adaptation/save", data={
            "tk_number": "EDIT-001",
            "csrf_token": token,
        }, follow_redirects=False)
        loc = r.headers.get("location", "")
        card_id = loc.strip("/").split("/")[1] if "/adaptation/" in loc else None
        if not card_id:
            pytest.skip("Не удалось создать карточку")
        r2 = client.get(f"/adaptation/{card_id}/edit")
        assert r2.status_code == 200
        assert "EDIT-001" in r2.text


class TestAdaptationDelete:
    def _create_and_get_id(self, client):
        _login(client)
        r = client.get("/adaptation/new")
        import re
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
        token = m.group(1) if m else ""
        r2 = client.post("/adaptation/save", data={
            "tk_number": "DEL-001", "csrf_token": token,
        }, follow_redirects=False)
        loc = r2.headers.get("location", "")
        parts = loc.strip("/").split("/")
        return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None

    def test_delete_card(self, client):
        card_id = self._create_and_get_id(client)
        if not card_id:
            pytest.skip("Не удалось создать карточку")
        r = client.get("/adaptation/new")
        import re
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
        token = m.group(1) if m else ""
        r2 = client.post(f"/adaptation/{card_id}/delete",
                         data={"csrf_token": token},
                         follow_redirects=False)
        assert r2.status_code in (302, 303)
        r3 = client.get("/adaptation")
        assert "DEL-001" not in r3.text

    def test_delete_nonexistent_returns_redirect(self, client):
        _login(client)
        r = client.get("/adaptation/new")
        import re
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
        token = m.group(1) if m else ""
        r2 = client.post("/adaptation/9999/delete",
                         data={"csrf_token": token},
                         follow_redirects=False)
        assert r2.status_code in (302, 303)


class TestAdaptationDownload:
    def test_download_returns_xlsx(self, client):
        _login(client)
        r = client.get("/adaptation/new")
        import re
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
        token = m.group(1) if m else ""
        r2 = client.post("/adaptation/save", data={
            "tk_number": "DL-001", "csrf_token": token,
            "recon_type": "Реконструкция",
        }, follow_redirects=False)
        loc = r2.headers.get("location", "")
        parts = loc.strip("/").split("/")
        card_id = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
        if not card_id:
            pytest.skip("Не удалось создать карточку")
        r3 = client.get(f"/adaptation/{card_id}/download")
        assert r3.status_code == 200
        assert "spreadsheetml" in r3.headers.get("content-type", "")
