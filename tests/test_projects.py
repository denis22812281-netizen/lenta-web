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
    from urllib.parse import unquote
    big_file = b"X" * (11 * 1024 * 1024)  # 11 MB
    r = auth_client.post(
        "/import-reconstruct",
        files={"file": ("big.xlsx", big_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    location = unquote(r.headers.get("location", ""))
    assert "большой" in location


# ─── Новые тесты безопасности ─────────────────────────────────────────────────

def test_export_excel_requires_auth(client):
    """Экспорт проектов должен требовать авторизацию."""
    r = client.get("/api/export/projects-excel", follow_redirects=False)
    assert r.status_code == 302


def test_export_excel_returns_xlsx_when_authed(auth_client):
    """Авторизованный пользователь получает xlsx-файл."""
    r = auth_client.get("/api/export/projects-excel")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_bulk_update_rejects_invalid_status(auth_client):
    """bulk-update должен отклонять произвольные строки статуса."""
    r = auth_client.post("/api/projects/bulk-update",
                         json={"ids": [], "action": "status:ХАКЕР"})
    assert r.status_code == 400
    data = r.json()
    assert data["ok"] is False


def test_bulk_update_accepts_valid_status(auth_client):
    """bulk-update принимает статус из списка STATUSES (создаём проект для теста)."""
    from tests.conftest import TestingSessionLocal
    import models

    # Создаём временный проект
    auth_client.post("/projects/create", data={
        "name": "Тест bulk-update", "tk_number": "BULK1", "city": "Москва",
        "project_type": "Констракшн", "status": "Планирование",
    }, follow_redirects=False)

    db = TestingSessionLocal()
    p = db.query(models.Project).filter_by(tk_number="BULK1").first()
    pid = p.id if p else None
    db.close()

    if pid:
        r = auth_client.post("/api/projects/bulk-update",
                             json={"ids": [pid], "action": "status:Активный"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Убираем за собой
        auth_client.post(f"/projects/{pid}/delete", follow_redirects=False)


def test_project_detail_404_for_unknown(auth_client):
    r = auth_client.get("/projects/99999")
    assert r.status_code == 404


# ─── История изменений ────────────────────────────────────────────────────────

def _create_temp_project(auth_client, tk="TMP_HIST"):
    auth_client.post("/projects/create", data={
        "name": f"Тест {tk}", "tk_number": tk, "city": "Тест",
        "project_type": "Констракшн", "status": "Активный",
    }, follow_redirects=False)
    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    p = db.query(models.Project).filter_by(tk_number=tk).first()
    pid = p.id if p else None
    db.close()
    return pid


def test_history_recorded_on_update(auth_client):
    """Изменение поля проекта создаёт запись в project_history."""
    pid = _create_temp_project(auth_client, "TMP_HIST1")
    assert pid, "Проект не создан"

    auth_client.post(f"/projects/{pid}/update", data={
        "name": "Новое имя TMP_HIST1", "tk_number": "TMP_HIST1",
        "city": "Москва", "project_type": "Констракшн", "status": "Активный",
    }, follow_redirects=False)

    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    history = db.query(models.ProjectHistory).filter_by(project_id=pid).all()
    db.close()
    assert any(h.field_label for h in history), "История изменений не записана"
    auth_client.post(f"/projects/{pid}/delete", follow_redirects=False)


# ─── Комментарии ─────────────────────────────────────────────────────────────

def test_comment_add_and_delete(auth_client):
    """Добавление и удаление комментария к проекту."""
    pid = _create_temp_project(auth_client, "TMP_CMT1")
    assert pid

    r = auth_client.post(f"/projects/{pid}/comments/add",
                         data={"text": "Тестовый комментарий"}, follow_redirects=False)
    assert r.status_code in (302, 303)

    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    comment = db.query(models.ProjectComment).filter_by(project_id=pid).first()
    db.close()
    assert comment is not None
    assert comment.text == "Тестовый комментарий"

    r = auth_client.post(f"/projects/{pid}/comments/{comment.id}/delete",
                         follow_redirects=False)
    assert r.status_code in (302, 303)

    db = TestingSessionLocal()
    gone = db.query(models.ProjectComment).filter_by(id=comment.id).first()
    db.close()
    assert gone is None
    auth_client.post(f"/projects/{pid}/delete", follow_redirects=False)


# ─── Вложения ─────────────────────────────────────────────────────────────────

def test_attachment_upload_and_delete(auth_client):
    """Загрузка и удаление вложения к проекту."""
    pid = _create_temp_project(auth_client, "TMP_ATT1")
    assert pid

    img_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = auth_client.post(
        f"/projects/{pid}/attachments/upload",
        files={"file": ("test.png", img_bytes, "image/png")},
        follow_redirects=False,
    )
    assert r.status_code in (200, 302, 303), f"Upload failed: {r.status_code}"

    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    att = db.query(models.ProjectAttachment).filter_by(project_id=pid).first()
    db.close()
    assert att is not None
    assert att.file_type == "image"

    r = auth_client.post(f"/projects/{pid}/attachments/{att.id}/delete",
                         follow_redirects=False)
    assert r.status_code in (302, 303)

    db = TestingSessionLocal()
    gone = db.query(models.ProjectAttachment).filter_by(id=att.id).first()
    db.close()
    assert gone is None
    auth_client.post(f"/projects/{pid}/delete", follow_redirects=False)


# ─── Gantt: обновление дат этапа ─────────────────────────────────────────────

def test_stage_date_update_via_api(auth_client):
    """AJAX-эндпоинт /api/stages/{id}/dates обновляет даты этапа."""
    pid = _create_temp_project(auth_client, "TMP_GANTT")
    assert pid

    r = auth_client.post(f"/projects/{pid}/stages/add", data={
        "name": "Этап 1", "start_date": "2026-07-01", "end_date": "2026-07-31",
        "stage_status": "Запланировано",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)

    from tests.conftest import TestingSessionLocal
    import models
    db = TestingSessionLocal()
    stage = db.query(models.ProjectStage).filter_by(project_id=pid).first()
    db.close()
    assert stage is not None
    sid = stage.id

    r = auth_client.post(f"/api/stages/{sid}/dates",
                         json={"start": "2026-08-01", "end": "2026-08-31"})
    assert r.status_code == 200
    assert r.json().get("ok") is True

    db = TestingSessionLocal()
    from datetime import date
    updated = db.query(models.ProjectStage).filter_by(id=sid).first()
    db.close()
    assert updated.start_date == date(2026, 8, 1)
    assert updated.end_date == date(2026, 8, 31)
    auth_client.post(f"/projects/{pid}/delete", follow_redirects=False)
