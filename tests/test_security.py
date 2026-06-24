"""Unit tests for security components: magic bytes validation and CSRF middleware."""
import os

import pytest

# ─── Magic bytes ──────────────────────────────────────────────────────────────
from utils.files import check_magic_bytes

# Minimal valid file signatures (magic bytes)
_JPEG_MAGIC = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 508
_PNG_MAGIC  = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"\x00" * 504
_PDF_MAGIC  = b"%PDF-1.4\n" + b"\x00" * 503
_ZIP_MAGIC  = bytes([0x50, 0x4B, 0x03, 0x04]) + b"\x00" * 508  # XLSX is a ZIP
_TEXT       = b"Hello, world! Plain text file.\n" * 20


def test_valid_jpeg_passes():
    check_magic_bytes(_JPEG_MAGIC, "photo.jpg")


def test_valid_jpeg_uppercase_ext_passes():
    check_magic_bytes(_JPEG_MAGIC, "photo.JPG")


def test_valid_png_passes():
    check_magic_bytes(_PNG_MAGIC, "image.png")


def test_valid_pdf_passes():
    check_magic_bytes(_PDF_MAGIC, "doc.pdf")


def test_text_file_passes_unidentified():
    # filetype.guess returns None for plain text → should not raise
    check_magic_bytes(_TEXT, "notes.txt")


def test_pdf_disguised_as_jpg_raises():
    with pytest.raises(ValueError, match="не является изображением"):
        check_magic_bytes(_PDF_MAGIC, "evil.jpg")


def test_jpeg_disguised_as_pdf_raises():
    with pytest.raises(ValueError, match="не является PDF"):
        check_magic_bytes(_JPEG_MAGIC, "evil.pdf")


def test_zip_as_xlsx_passes():
    # XLSX is a ZIP internally — filetype guesses application/zip or office type
    # Our check allows zip-family for xlsx; should not raise
    check_magic_bytes(_ZIP_MAGIC, "table.xlsx")


def test_jpeg_disguised_as_docx_does_not_raise():
    # .docx is in _DOC_EXTS but not in the explicitly checked set → pass-through
    check_magic_bytes(_JPEG_MAGIC, "report.docx")


# ─── CSRF middleware ──────────────────────────────────────────────────────────
# We must test with TESTING=0 to actually exercise the middleware.

@pytest.fixture
def csrf_client():
    """Client with CSRF enforcement enabled (TESTING env var cleared)."""
    original = os.environ.pop("TESTING", None)
    try:
        from fastapi.testclient import TestClient

        from database import get_db
        from main import app
        from tests.conftest import override_get_db
        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        if original is not None:
            os.environ["TESTING"] = original


def _get_csrf_token(client):
    """Login and extract csrf_token from session."""
    import models
    import utils.passwords as pw
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    phone = "+79991111111"
    if not db.query(models.PhoneWhitelist).filter_by(phone=phone).first():
        db.add(models.PhoneWhitelist(phone=phone, display_name="CSRF Test User", is_admin=False))
        db.commit()
    if not db.query(models.User).filter_by(phone=phone).first():
        u = models.User(phone=phone, username=phone,
                        password_hash=pw.hash_password("pass4csrf"),
                        display_name="CSRF Test User", is_admin=False)
        db.add(u); db.commit()
    db.close()

    client.post("/login/check-phone", data={"phone": phone})
    client.post("/login/enter", data={"phone": phone, "password": "pass4csrf"})

    r = client.get("/")
    # csrf_token is in the session cookie — extract from response meta tag
    import re
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', r.text)
    return m.group(1) if m else None


def test_csrf_blocks_post_without_token(csrf_client):
    """POST to a protected route without any CSRF token must return 403."""
    _get_csrf_token(csrf_client)  # login first
    r = csrf_client.post("/tasks/create", data={"title": "x"})
    assert r.status_code == 403


def test_csrf_accepts_header_token(csrf_client):
    """POST with X-CSRFToken header must not be rejected by CSRF middleware."""
    token = _get_csrf_token(csrf_client)
    assert token, "Could not obtain CSRF token from page"
    r = csrf_client.post(
        "/tasks/create",
        data={"title": "csrf header test", "priority": "medium"},
        headers={"X-CSRFToken": token},
    )
    # 200 or redirect → CSRF passed (may fail validation for other reasons)
    assert r.status_code != 403, f"CSRF middleware rejected valid header token (got {r.status_code})"


def test_csrf_accepts_form_body_token(csrf_client):
    """POST with csrf_token in form body must not be rejected by CSRF middleware."""
    token = _get_csrf_token(csrf_client)
    assert token
    r = csrf_client.post(
        "/tasks/create",
        data={"title": "csrf body test", "priority": "medium", "csrf_token": token},
    )
    assert r.status_code != 403


def test_csrf_rejects_wrong_token(csrf_client):
    """POST with a forged token must return 403."""
    _get_csrf_token(csrf_client)
    r = csrf_client.post(
        "/tasks/create",
        data={"title": "x"},
        headers={"X-CSRFToken": "forged-token-abc123"},
    )
    assert r.status_code == 403
